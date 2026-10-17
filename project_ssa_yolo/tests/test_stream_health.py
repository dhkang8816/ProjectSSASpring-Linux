import os
import threading
import unittest
from unittest.mock import patch

from apps.app import create_app
from apps.stream import views


class StreamHealthRouteTest(unittest.TestCase):

    def test_runtime_initialization_requires_token_and_starts_workers_asynchronously(self):
        started = threading.Event()
        token = "x" * 32
        with patch.dict(os.environ, {"SSA_FLASK_CONTROL_TOKEN": token}, clear=False), \
                patch.object(views.yolo_detector, "initialize_ai_runtime"), \
                patch.object(views.yolo_detector, "get_ai_runtime_status", return_value={
                    "ready": True, "stage": "AI_READY", "progress": 90, "label": "test ready"}), \
                patch("apps.services.starter.start_services", side_effect=started.set):
            app = create_app("testing")
            client = app.test_client()

            denied = client.post("/stream/admin/initialize")
            self.assertEqual(403, denied.status_code)

            accepted = client.post(
                "/stream/admin/initialize",
                headers={"X-SSA-Flask-Control-Token": token},
            )
            self.assertEqual(200, accepted.status_code)
            self.assertEqual("SUCCESS", accepted.get_json()["status"])
            self.assertTrue(started.wait(1.0))

            status = client.get(
                "/stream/admin/startup-status",
                headers={"X-SSA-Flask-Control-Token": token},
            )

        self.assertEqual(200, status.status_code)
        self.assertEqual("SUCCESS", status.get_json()["status"])
        self.assertTrue(status.get_json()["servicesStarted"])

    def test_ai_profile_has_no_sqlite_initialization_and_preserves_stream_routes(self):
        with patch.dict(os.environ, {"SSA_SQLITE_PATH": "", "SSA_TEST_SQLITE_PATH": ""}), \
                patch("apps.config.LocalConfig.database_uri", side_effect=AssertionError("legacy DB invoked")), \
                patch("apps.services.starter.start_services") as start:
            app = create_app("ai")
            self.assertNotIn("sqlalchemy", app.extensions)
            self.assertNotIn("migrate", app.extensions)
            self.assertNotIn("auth", app.blueprints)
            self.assertIn("stream", app.blueprints)
            client = app.test_client()
            self.assertEqual("ai", client.get("/").get_json()["profile"])
            self.assertEqual("ai", client.get("/stream/").get_json()["profile"])
            self.assertEqual("ai", client.get("/esp32_yolov12/").get_json()["profile"])
            self.assertEqual(200, client.get("/stream/health").status_code)
            self.assertEqual(404, client.get("/auth/login").status_code)

    def test_legacy_testing_profile_keeps_db_and_ui(self):
        app = create_app("testing")
        self.assertIn("sqlalchemy", app.extensions)
        for blueprint in ("auth", "crud", "detect_data", "main", "control_page"):
            self.assertIn(blueprint, app.blueprints)

    def test_shutdown_requires_token_and_uses_runtime_callback(self):
        shutdown_called = threading.Event()
        with patch.dict(os.environ, {"SSA_FLASK_CONTROL_TOKEN": "x" * 32}, clear=False), \
                patch("apps.services.starter.start_services") as start_services:
            app = create_app("testing")
            client = app.test_client()

            denied = client.post("/stream/admin/shutdown")
            self.assertEqual(403, denied.status_code)

            app.config["SSA_SERVER_SHUTDOWN"] = shutdown_called.set
            accepted = client.post(
                "/stream/admin/shutdown",
                headers={"X-SSA-Flask-Control-Token": "x" * 32},
            )

        self.assertEqual(200, accepted.status_code)
        self.assertEqual("SUCCESS", accepted.get_json()["status"])
        self.assertTrue(shutdown_called.wait(1.0))
        start_services.assert_not_called()

    def test_existing_optional_services_do_not_skip_ai_initialization(self):
        ai = {"ready": False, "stage": "AI_IDLE", "progress": 0, "label": "waiting"}
        warmed = threading.Event()
        def warmup():
            ai.update(ready=True, stage="AI_READY")
            warmed.set()
        with patch.dict(os.environ, {"SSA_FLASK_CONTROL_TOKEN": "x" * 32}), \
                patch("apps.services.starter.start_services"), \
                patch.object(views.yolo_detector, "initialize_ai_runtime", side_effect=warmup) as initialize, \
                patch.object(views.yolo_detector, "get_ai_runtime_status", side_effect=lambda: dict(ai)), \
                patch.object(views.sensor_helper, "get_latest_battery_status", return_value={}):
            client = create_app("testing").test_client()
            client.get("/stream/battery/status")
            response = client.post("/stream/admin/initialize", headers={"X-SSA-Flask-Control-Token": "x" * 32})
            self.assertEqual(200, response.status_code)
            self.assertTrue(warmed.wait(1))
            initialize.assert_called_once()

    def test_ai_failure_is_reported_without_starting_optional_io(self):
        ai = {"ready": False, "stage": "AI_IDLE", "progress": 0, "label": "waiting"}
        failed = threading.Event()
        def warmup():
            ai.update(stage="AI_FAILED", error="CUDA unavailable")
            failed.set()
            raise RuntimeError("CUDA unavailable")
        with patch.dict(os.environ, {"SSA_FLASK_CONTROL_TOKEN": "x" * 32}), \
                patch("apps.services.starter.start_services") as start, \
                patch.object(views.yolo_detector, "initialize_ai_runtime", side_effect=warmup), \
                patch.object(views.yolo_detector, "get_ai_runtime_status", side_effect=lambda: dict(ai)):
            client = create_app("testing").test_client()
            headers = {"X-SSA-Flask-Control-Token": "x" * 32}
            client.post("/stream/admin/initialize", headers=headers)
            self.assertTrue(failed.wait(1))
            payload = client.get("/stream/admin/startup-status", headers=headers).get_json()
            self.assertFalse(payload["aiReady"])
            self.assertFalse(payload["ready"])
            self.assertEqual("AI_FAILED", payload["stage"])
            start.assert_not_called()

    def test_health_returns_cached_status_without_starting_services(self):
        with patch("apps.services.starter.start_services") as start_services, \
                patch.object(views.yolo_detector, "get_default_source_key", return_value="video_1"), \
                patch.object(views.yolo_detector, "get_source_status", return_value={"video_1": {"running": True}}), \
                patch.object(views.sensor_helper, "get_sensor_service_status", return_value={"sensorOnline": True}), \
                patch.object(views.buzzer_helper, "get_buzzer_status", return_value={"enabled": True}), \
                patch.object(views.notifier, "get_notification_status", return_value={"configured": True}), \
                patch.object(views.yolo_detector, "start_source_worker") as start_yolo, \
                patch.object(views.buzzer_helper, "start_buzzer_service") as start_buzzer:
            app = create_app("testing")
            response = app.test_client().get("/stream/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual("video_1", response.get_json()["default_source"])
        self.assertTrue(response.get_json()["sensor"]["sensorOnline"])
        start_services.assert_not_called()
        start_yolo.assert_not_called()
        start_buzzer.assert_not_called()

    def test_health_and_startup_status_share_actual_ai_state_without_control_token(self):
        ai = {"ready": True, "stage": "AI_READY", "progress": 90, "label": "ready", "device": "cuda:0"}
        with patch.object(views.yolo_detector, "get_ai_runtime_status", side_effect=lambda: dict(ai)), \
                patch("apps.services.starter.start_services") as start:
            client = create_app("testing").test_client()
            response = client.get("/stream/health")
            payload = response.get_json()
            self.assertTrue(payload["processReady"])
            self.assertTrue(payload["aiReady"])
            self.assertFalse(payload["ready"])  # optional services have not started
            self.assertEqual("cuda:0", payload["ai"]["device"])
            self.assertEqual("no-store", response.headers["Cache-Control"])
            self.assertIn("instanceId", payload)
            self.assertIn("reports", payload)
            ai.update(ready=False, stage="AI_FAILED", error="CUDA unavailable")
            payload = client.get("/stream/health").get_json()
            self.assertFalse(payload["aiReady"])
            self.assertFalse(payload["ready"])
            start.assert_not_called()

    def test_battery_route_returns_cached_status_without_direct_serial_access(self):
        battery = {
            "available": True,
            "voltage": 3.91,
            "percent": 73.5,
            "status": "NORMAL",
            "updatedAt": 1,
            "sourceKey": "esp32",
        }
        with patch("apps.services.starter.start_services") as start_services, \
                patch.object(views.sensor_helper, "get_latest_battery_status", return_value=battery) as cached_battery:
            app = create_app("testing")
            response = app.test_client().get("/stream/battery/status")

        self.assertEqual(200, response.status_code)
        self.assertEqual(73.5, response.get_json()["percent"])
        cached_battery.assert_called_once_with()
        start_services.assert_called_once()


if __name__ == "__main__":
    unittest.main()
