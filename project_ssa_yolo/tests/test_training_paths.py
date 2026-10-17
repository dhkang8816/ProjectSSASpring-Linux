"""Training path checks without importing or running the real model."""

import sys
from types import ModuleType
from unittest.mock import Mock

import pytest

from train import train as training


def test_missing_training_inputs_fail_before_model_import(tmp_path, monkeypatch):
    monkeypatch.setattr(training, "PROJECT_ROOT", tmp_path)
    fake_library = ModuleType("ultralytics")
    fake_library.YOLO = Mock()
    monkeypatch.setitem(sys.modules, "ultralytics", fake_library)

    with pytest.raises(FileNotFoundError, match="Training weights"):
        training.train_yolov12()

    fake_library.YOLO.assert_not_called()


def test_training_output_is_project_relative_not_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr(training, "PROJECT_ROOT", tmp_path)
    (tmp_path / "yolo12n.pt").write_bytes(b"unit-test-placeholder")
    dataset = tmp_path / "train" / "dataset"
    dataset.mkdir(parents=True)
    (dataset / "data.yaml").write_text("# path test only\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    fake_library = ModuleType("ultralytics")
    fake_library.YOLO = Mock()
    monkeypatch.setitem(sys.modules, "ultralytics", fake_library)
    shutdown = Mock()
    monkeypatch.setattr(training.os, "system", shutdown)

    training.train_yolov12()

    kwargs = fake_library.YOLO.return_value.train.call_args.kwargs
    assert kwargs["project"] == str(tmp_path / "my_yolov12_project")
    assert kwargs["data"] == str(dataset / "data.yaml")
    if training.os.name != "nt":
        shutdown.assert_not_called()
