"""CUDA selection and AI readiness checks without using hardware or models."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from apps.services import yolo_detector as detector
from apps.services.inference_device import resolve_device


def test_requested_cuda_never_falls_back_to_cpu():
    torch = SimpleNamespace(cuda=Mock(), ones=Mock())
    torch.cuda.is_available.return_value = False
    with pytest.raises(RuntimeError, match="CUDA is unavailable"):
        resolve_device("cuda:0", torch)
    torch.ones.assert_not_called()


def test_cpu_is_an_explicit_choice():
    torch = SimpleNamespace(cuda=Mock())
    assert resolve_device("cpu", torch) == "cpu"
    torch.cuda.is_available.assert_not_called()


def test_cuda_checks_device_index_and_tensor_arithmetic():
    cuda = Mock()
    cuda.is_available.return_value = True
    cuda.device_count.return_value = 1
    torch = SimpleNamespace(cuda=cuda, ones=Mock(return_value=np.ones((8, 8))),
                            all=lambda value: np.all(value))
    assert resolve_device("0", torch) == "cuda:0"
    cuda.synchronize.assert_called_once_with(0)
    with pytest.raises(RuntimeError, match="GPU index"):
        resolve_device("cuda:3", torch)


@pytest.fixture
def isolated_model(monkeypatch):
    monkeypatch.setattr(detector, "_model", None)
    monkeypatch.setattr(detector, "_model_device", None)
    monkeypatch.setattr(detector, "_ai_status", {"stage": "AI_IDLE", "ready": False,
                        "progress": 0, "label": "waiting", "error": None})


def test_four_callers_share_one_model_and_one_device_initialization(monkeypatch, isolated_model, tmp_path):
    path = tmp_path / "trusted.pt"
    path.touch()
    model = Mock(return_value=[])
    model.names = dict(enumerate(detector.YOLO_TO_CODE))
    constructor = Mock(return_value=model)
    device = Mock(return_value="cpu")
    monkeypatch.setattr(detector.runtime_settings, "YOLO_MODEL_PATH", str(path))
    monkeypatch.setattr(detector, "YOLO", constructor)
    monkeypatch.setattr(detector, "resolve_device", device)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(detector._run_inference, [object()] * 4))
    constructor.assert_called_once_with(str(path))
    device.assert_called_once()
    model.to.assert_called_once_with("cpu")
    assert model.call_count == 4


def test_ai_ready_requires_completed_inference(monkeypatch, isolated_model):
    model = SimpleNamespace(model=SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device="cpu")])),
                            names=dict(enumerate(detector.YOLO_TO_CODE)))
    def infer(frame):
        assert not detector.get_ai_runtime_status()["ready"]
        detector._model = model
        detector._model_device = "cpu"
    warmup = Mock(side_effect=infer)
    monkeypatch.setattr(detector, "_run_inference", warmup)
    assert detector.initialize_ai_runtime()["ready"]
    assert detector.initialize_ai_runtime()["ready"]
    warmup.assert_called_once()


def test_failed_initialization_is_visible_and_does_not_start_capture(monkeypatch, isolated_model, tmp_path):
    monkeypatch.setattr(detector, "_run_inference", Mock(side_effect=RuntimeError("CUDA unavailable")))
    with pytest.raises(RuntimeError):
        detector.initialize_ai_runtime()
    assert not detector.get_ai_runtime_status()["ready"]
    assert detector.get_ai_runtime_status()["stage"] == "AI_FAILED"
    path = tmp_path / "model.pt"
    path.touch()
    monkeypatch.setattr(detector.runtime_settings, "YOLO_MODEL_PATH", str(path))
    worker = detector.SourceWorker("esp32", {"mode": "esp32", "uri": "http://unused.invalid"})
    assert not worker.start()
    assert worker.thread is None
    assert "CUDA" in worker.status()["last_error"]


def test_shutdown_joins_sources_then_releases_model_and_cuda_cache(monkeypatch, isolated_model):
    monkeypatch.setattr(detector, "_model", object())
    monkeypatch.setattr(detector, "_model_device", "cuda:0")
    stop = Mock(return_value={"video_1": {"running": False}})
    monkeypatch.setattr(detector, "stop_all_workers", stop)
    empty = Mock()
    monkeypatch.setattr(detector.torch.cuda, "empty_cache", empty)
    detector.shutdown_ai_runtime()
    stop.assert_called_once()
    empty.assert_called_once()
    assert detector._model is None
    assert not detector.get_ai_runtime_status()["ready"]


def test_shutdown_does_not_release_a_model_still_used_by_a_stopping_worker(monkeypatch, isolated_model):
    model = object()
    monkeypatch.setattr(detector, "_model", model)
    monkeypatch.setattr(detector, "_model_device", "cuda:0")
    monkeypatch.setattr(detector, "stop_all_workers", Mock(return_value={
        "esp32": {"running": False, "stopping": True}}))
    empty = Mock()
    monkeypatch.setattr(detector.torch.cuda, "empty_cache", empty)
    with pytest.raises(RuntimeError, match="still stopping"):
        detector.shutdown_ai_runtime()
    assert detector._model is model
    empty.assert_not_called()
