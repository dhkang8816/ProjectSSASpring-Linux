"""The operational path inspector must never prepare the paths it inspects."""

from scripts.diagnostics import path_check


def test_inspecting_a_missing_store_does_not_create_it(tmp_path):
    missing = tmp_path / "missing" / "uploads"
    name, status = path_check.inspect_path("SSA_UPLOAD_ROOT", str(missing), directory=True, writable=True)
    assert name == "SSA_UPLOAD_ROOT"
    assert status.startswith("MISSING")
    assert not (tmp_path / "missing").exists()


def test_readable_existing_file_is_checked_without_modifying_it(tmp_path):
    asset = tmp_path / "model.pt"
    asset.write_bytes(b"unit test only")
    before = asset.stat()
    assert path_check.inspect_path("SSA_YOLO_MODEL_PATH", str(asset))[1] == "OK"
    assert asset.read_bytes() == b"unit test only"
    assert asset.stat().st_mtime_ns == before.st_mtime_ns


def test_relative_files_are_resolved_from_repository_root(tmp_path, monkeypatch):
    (tmp_path / "model.pt").touch()
    monkeypatch.setattr(path_check, "REPOSITORY_ROOT", tmp_path)
    assert path_check.inspect_path("SSA_YOLO_MODEL_PATH", "model.pt")[1] == "OK"


def test_database_requires_parent_write_permission(tmp_path, monkeypatch):
    database = tmp_path / "existing.sqlite"
    database.touch()
    monkeypatch.setattr(path_check.os, "access", lambda path, mode: path != tmp_path)
    assert path_check.inspect_path("SSA_SQLITE_PATH", str(database), writable=True)[1] == "NO_PARENT_WRITE_OR_SEARCH_ACCESS"
