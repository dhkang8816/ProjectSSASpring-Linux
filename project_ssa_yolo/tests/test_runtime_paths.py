"""Local path regression checks: no models, devices, services, or DB connections."""

import ast
import os
import sqlite3
import importlib.util
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from apps import environment, runtime_settings
from apps.config import LocalConfig, TestingConfig, sqlite_database_uri
from apps.services import buzzer_helper


def _isolated_definitions(relative_file, names, dependencies):
    """Load helpers without importing service modules that register live workers."""
    source = (runtime_settings.PROJECT_ROOT / relative_file).read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    for node in selected:
        node.decorator_list = []
    namespace = dict(dependencies)
    exec(compile(ast.Module(body=selected, type_ignores=[]), relative_file, "exec"), namespace)
    return namespace


class RuntimePathTest(unittest.TestCase):
    def test_environment_file_is_project_anchored_and_shell_wins(self):
        with patch.object(environment, "load_dotenv") as load:
            environment.load_project_environment()
        load.assert_called_once_with(dotenv_path=environment.PROJECT_ROOT / ".env", override=False)

    def test_relative_files_are_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as cwd:
            project = Path(project)
            model = project / "model.pt"
            model.touch()
            previous_cwd = Path.cwd()
            try:
                os.chdir(cwd)
                with patch.object(runtime_settings, "REPOSITORY_ROOT", project):
                    self.assertEqual(model, runtime_settings.readable_file("SSA_YOLO_MODEL_PATH", "model.pt"))
            finally:
                os.chdir(previous_cwd)

    @unittest.skipIf(os.name == "nt", "Windows accepts drive paths")
    def test_windows_path_is_rejected_on_linux_without_disclosing_value(self):
        invalid_value = "C:/legacy/private-video.mp4"
        with self.assertRaises(runtime_settings.RuntimePathError) as raised:
            runtime_settings.readable_file("SSA_VIDEO_1_PATH", invalid_value)
        self.assertIn("SSA_VIDEO_1_PATH", str(raised.exception))
        self.assertNotIn(invalid_value, str(raised.exception))

    def test_url_is_not_accepted_as_a_local_file(self):
        with self.assertRaises(runtime_settings.RuntimePathError):
            runtime_settings.filesystem_path("SSA_YOLO_MODEL_PATH", "https://example.invalid/model.pt")

    def test_missing_file_is_not_replaced_with_a_default(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.pt"
            with self.assertRaises(runtime_settings.RuntimePathError):
                runtime_settings.readable_file("SSA_YOLO_MODEL_PATH", missing)
            self.assertFalse(missing.exists())

    def test_unreadable_file_reports_the_setting_name(self):
        with tempfile.NamedTemporaryFile() as file, patch.object(runtime_settings.os, "access", return_value=False):
            with self.assertRaisesRegex(runtime_settings.RuntimePathError, "SSA_VIDEO_2_PATH"):
                runtime_settings.readable_file("SSA_VIDEO_2_PATH", file.name)

    def test_upload_root_must_be_explicit_and_absolute(self):
        for value in ("", "relative-uploads"):
            with self.subTest(value=value), patch.object(runtime_settings, "UPLOAD_ROOT", value):
                with self.assertRaisesRegex(runtime_settings.RuntimePathError, "SSA_UPLOAD_ROOT"):
                    runtime_settings.upload_directory("detection", create=True)

    def test_snapshot_directory_is_created_only_under_configured_root(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime_settings, "UPLOAD_ROOT", directory):
            result = runtime_settings.upload_directory("dangerlog", create=True)
            self.assertEqual(Path(directory) / "dangerlog", result)
            self.assertTrue(result.is_dir())

    @unittest.skipIf(os.name == "nt", "Creating symlinks requires extra Windows privileges")
    def test_snapshot_category_cannot_follow_a_symlink_outside_root(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            (Path(directory) / "detection").symlink_to(external, target_is_directory=True)
            with patch.object(runtime_settings, "UPLOAD_ROOT", directory):
                with self.assertRaises(runtime_settings.RuntimePathError):
                    runtime_settings.upload_directory("detection", create=True)

    def test_explicit_sqlite_path_requires_existing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "external.sqlite"
            with patch.dict(os.environ, {"SSA_SQLITE_PATH": str(database)}):
                with self.assertRaisesRegex(runtime_settings.RuntimePathError, "SSA_SQLITE_PATH"):
                    sqlite_database_uri("SSA_SQLITE_PATH")
                self.assertFalse(database.exists())
                database.touch()
                self.assertEqual(f"sqlite:///{database.as_posix()}", sqlite_database_uri("SSA_SQLITE_PATH"))

    def test_unconfigured_database_is_not_created_from_a_guessed_location(self):
        with patch.dict(os.environ, {"SSA_SQLITE_PATH": "", "SSA_TEST_SQLITE_PATH": ""}):
            with self.assertRaisesRegex(runtime_settings.RuntimePathError, "SSA_SQLITE_PATH"):
                LocalConfig.database_uri()
            self.assertEqual("sqlite:///:memory:", TestingConfig.database_uri())

    def test_upload_default_resolution_does_not_create_a_directory(self):
        with tempfile.TemporaryDirectory() as parent:
            missing = Path(parent) / "uploads"
            with patch.object(runtime_settings, "UPLOAD_ROOT", str(missing)):
                self.assertEqual(missing / "detection", runtime_settings.upload_directory("detection"))
            self.assertFalse(missing.exists())

    def test_production_configuration_does_not_validate_the_testing_store(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "production.sqlite"
            database.touch()
            with patch.dict(os.environ, {
                "SSA_SQLITE_PATH": str(database),
                "SSA_TEST_SQLITE_PATH": str(Path(directory) / "missing-testing.sqlite"),
            }):
                self.assertEqual(f"sqlite:///{database.as_posix()}", LocalConfig.database_uri())

    def test_testing_configuration_does_not_validate_the_production_store(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "testing.sqlite"
            database.touch()
            with patch.dict(os.environ, {
                "SSA_SQLITE_PATH": str(Path(directory) / "missing-production.sqlite"),
                "SSA_TEST_SQLITE_PATH": str(database),
            }):
                self.assertEqual(f"sqlite:///{database.as_posix()}", TestingConfig.database_uri())

    @unittest.skipIf(os.name == "nt", "COM device names are valid on Windows")
    def test_stale_com_name_is_blocked_before_subprocess_execution(self):
        with patch.object(buzzer_helper.subprocess, "run") as run:
            with self.assertRaisesRegex(runtime_settings.RuntimePathError, "SSA_ESP32_COM_PORT"):
                buzzer_helper.run_mpremote(("connect", "COM77", "version"))
        run.assert_not_called()

    def test_windows_serial_configuration_remains_supported(self):
        with patch.object(runtime_settings.os, "name", "nt"):
            self.assertEqual("COM77", runtime_settings.validate_serial_port("COM77"))


class RuntimeSqlitePreparationTest(unittest.TestCase):
    def test_retained_copy_is_reused_only_if_schema_and_data_match(self):
        path = runtime_settings.REPOSITORY_ROOT / "project_ssa_spring/scripts/prepare-flask-sqlite-linux.py"
        spec = importlib.util.spec_from_file_location("ssa_sqlite_preparation", path)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite"
            destination = Path(directory) / "retained.sqlite"
            connection = sqlite3.connect(source)
            connection.execute("CREATE TABLE sample(value TEXT)")
            connection.execute("INSERT INTO sample VALUES ('original')")
            connection.commit()
            copied = sqlite3.connect(destination)
            connection.backup(copied)
            copied.close()
            connection.close()
            helper.validate_retained_copy(source, destination)
            connection = sqlite3.connect(destination)
            connection.execute("UPDATE sample SET value='changed'")
            connection.commit()
            connection.close()
            previous = destination.read_bytes()
            with self.assertRaises(SystemExit):
                helper.validate_retained_copy(source, destination)
            self.assertEqual(previous, destination.read_bytes())


class ServicePermissionProbeTest(unittest.TestCase):
    def test_write_probe_removes_only_its_own_temporary_file(self):
        helper_path = runtime_settings.REPOSITORY_ROOT / "project_ssa_spring/scripts/linux-runtime-permissions.py"
        spec = importlib.util.spec_from_file_location("ssa_permission_audit", helper_path)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "existing-user-image.png"
            existing.write_bytes(b"preserved user data")
            payload = {"identity": {"uid": 1, "gid": 1, "groups": []}, "umask": "0007",
                       "paths": [{"name": "upload", "path": directory, "directory": True, "writable": True}],
                       "verify": True, "full": False}
            previous_umask = os.umask(0o007)
            try:
                with patch.object(helper.os, "setgroups"), patch.object(helper.os, "setgid"), patch.object(helper.os, "setuid"):
                    result = helper.access_probe(payload)
            finally:
                os.umask(previous_umask)
            self.assertTrue(result["paths"][0]["write_probe"]["readback"])
            self.assertEqual([existing], list(Path(directory).iterdir()))
            self.assertEqual(b"preserved user data", existing.read_bytes())
            collision = Path(directory) / ".ssa-permission-probe-collision"
            collision.write_bytes(b"another process owns this file")
            previous_umask = os.umask(0o007)
            try:
                with patch.object(helper.os, "setgroups"), patch.object(helper.os, "setgid"), \
                        patch.object(helper.os, "setuid"), \
                        patch.object(helper.uuid, "uuid4", return_value=SimpleNamespace(hex="collision")):
                    result = helper.access_probe(payload)
            finally:
                os.umask(previous_umask)
            self.assertEqual("FileExistsError", result["paths"][0]["write_probe"]["error"])
            self.assertEqual(b"another process owns this file", collision.read_bytes())


class SnapshotPathTest(unittest.TestCase):
    def _helpers(self, cv2):
        return _isolated_definitions("apps/services/oracle_service.py", {"_save_physical_snapshot", "_local_snapshot_path"}, {
            "runtime_settings": runtime_settings, "uuid": uuid, "cv2": cv2,
        })

    def test_failed_imwrite_is_not_reported_as_a_saved_snapshot(self):
        cv2 = SimpleNamespace(imwrite=Mock(return_value=False))
        helpers = self._helpers(cv2)
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime_settings, "UPLOAD_ROOT", directory):
            with self.assertRaisesRegex(OSError, "SSA_UPLOAD_ROOT"):
                helpers["_save_physical_snapshot"](object(), "detection")
        cv2.imwrite.assert_called_once()

    def test_image_encoding_exception_does_not_expose_the_configured_path(self):
        cv2 = SimpleNamespace(imwrite=Mock(side_effect=RuntimeError("unredacted external path")))
        helpers = self._helpers(cv2)
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime_settings, "UPLOAD_ROOT", directory):
            with self.assertRaises(OSError) as raised:
                helpers["_save_physical_snapshot"](object(), "dangerlog")
        self.assertNotIn("unredacted", str(raised.exception))

    def test_saved_snapshot_lookup_rejects_parent_directory_traversal(self):
        helpers = self._helpers(SimpleNamespace())
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime_settings, "UPLOAD_ROOT", directory):
            with self.assertRaises(OSError):
                helpers["_local_snapshot_path"]("detection", "../other.jpg")

    def test_absent_frame_retains_the_existing_no_image_contract(self):
        helpers = self._helpers(SimpleNamespace(imwrite=Mock()))
        self.assertEqual("noImage.jpg", helpers["_save_physical_snapshot"](None, "detection"))


class DetectorPathTest(unittest.TestCase):
    def test_missing_weights_never_reaches_the_ultralytics_constructor(self):
        constructor = Mock()
        helpers = _isolated_definitions("apps/services/yolo_detector.py", {"_run_inference"}, {
            "runtime_settings": runtime_settings, "_model": None,
            "_model_inference_lock": threading.Lock(), "YOLO": constructor,
        })
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime_settings, "YOLO_MODEL_PATH", str(Path(directory) / "missing.pt")):
            with self.assertRaises(runtime_settings.RuntimePathError):
                helpers["_run_inference"](object())
        constructor.assert_not_called()

    def test_missing_video_never_reaches_opencv_capture(self):
        cv2 = SimpleNamespace(VideoCapture=Mock())
        helpers = _isolated_definitions("apps/services/yolo_detector.py", {"SourceWorker"}, {
            "runtime_settings": runtime_settings, "threading": threading,
            "cv2": cv2,
        })
        with tempfile.TemporaryDirectory() as directory:
            worker = helpers["SourceWorker"]("video_3", {"mode": "video", "uri": str(Path(directory) / "missing.mp4")})
            with self.assertRaisesRegex(runtime_settings.RuntimePathError, "SSA_VIDEO_3_PATH"):
                worker._open_capture()
        cv2.VideoCapture.assert_not_called()

    def test_invalid_model_prevents_worker_thread_start_and_exposes_status_error(self):
        helpers = _isolated_definitions("apps/services/yolo_detector.py", {"SourceWorker"}, {
            "runtime_settings": runtime_settings, "threading": threading,
        })
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime_settings, "YOLO_MODEL_PATH", str(Path(directory) / "missing.pt")):
            worker = helpers["SourceWorker"]("esp32", {"mode": "esp32", "uri": "http://camera.invalid/stream"})
            self.assertFalse(worker.start())
            self.assertIsNone(worker.thread)
            self.assertIn("SSA_YOLO_MODEL_PATH", worker.status()["last_error"])

    def test_failed_worker_start_does_not_select_a_different_default(self):
        helpers = _isolated_definitions("apps/services/yolo_detector.py", {"set_default_source"}, {
            "is_known_source": Mock(return_value=True), "start_source_worker": Mock(return_value=False),
            "_default_source_key": "video_1",
        })
        self.assertFalse(helpers["set_default_source"]("video_2"))
        self.assertEqual("video_1", helpers["_default_source_key"])

    def test_legacy_switch_endpoint_reports_configuration_failure(self):
        detector = SimpleNamespace(is_known_source=Mock(return_value=True), set_default_source=Mock(return_value=False))
        helpers = _isolated_definitions("apps/stream/views.py", {"change_hybrid_source"}, {
            "yolo_detector": detector, "jsonify": lambda payload: payload,
            "_status_payload": lambda: {"sources": {"video_1": {"last_error": "SSA_VIDEO_1_PATH"}}},
        })
        payload, status = helpers["change_hybrid_source"]("video_1")
        self.assertEqual(503, status)
        self.assertEqual("FAIL", payload["status"])

    def test_legacy_esp32_switch_reports_configuration_failure(self):
        detector = SimpleNamespace(set_default_source=Mock(return_value=False), get_source_status=Mock(return_value={}))
        start_receiver = Mock()
        helpers = _isolated_definitions("apps/esp32/views.py", {"change_mode_signal"}, {
            "yolo_detector": detector, "jsonify": lambda payload: payload,
            "start_esp32_receiver": start_receiver,
        })
        payload, status = helpers["change_mode_signal"]("esp32")
        self.assertEqual(503, status)
        self.assertEqual("FAIL", payload["status"])
        start_receiver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
