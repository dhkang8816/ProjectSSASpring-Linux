"""Offline four-worker GPU/MJPEG check. ESP32 is explicitly simulated locally."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--videos", type=Path, nargs=3, required=True)
    args = parser.parse_args()
    model = args.model.resolve(strict=True)
    with model.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != args.sha256:
            raise RuntimeError("Owner-trusted checkpoint fingerprint does not match")
    videos = [str(video.resolve(strict=True)) for video in args.videos]
    os.environ.update(SSA_YOLO_MODEL_PATH=str(model), SSA_YOLO_DEVICE="cuda:0", SSA_SQLITE_PATH="",
                      SSA_AUTO_START_DETECTION_WORKERS="false", SSA_OPTIONAL_IO_ENABLED="false",
                      YOLO_OFFLINE="true", YOLO_AUTOINSTALL="false")
    for index, video in enumerate(videos, 1):
        os.environ[f"SSA_VIDEO_{index}_PATH"] = video
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    def forbid_network(event, _args):
        if event in {"socket.connect", "subprocess.Popen"}:
            raise PermissionError("External IO is forbidden in the offline diagnostic")
    sys.addaudithook(forbid_network)

    import cv2
    import torch
    import ultralytics.utils
    ultralytics.utils.SETTINGS.update({"sync": False})
    from apps.app import create_app
    from apps.services import yolo_detector as detector

    app = create_app("ai")
    original_constructor = detector.YOLO

    class LocalEsp32Capture:
        """Match the MJPEG reader interface while using a looping local file."""
        last_error = None

        def __init__(self, *_args, **_kwargs):
            self.capture = cv2.VideoCapture(videos[0])

        def open(self):
            return self.capture.isOpened()

        def isOpened(self):
            return self.capture.isOpened()

        def read(self):
            success, frame = self.capture.read()
            if not success:
                self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                return self.capture.read()
            return success, frame

        def release(self):
            self.capture.release()

    with patch.object(detector, "YOLO", wraps=original_constructor) as constructor, \
            patch.object(detector, "init_ai_metadata_from_oracle"), \
            patch.object(detector, "process_detection_events"), \
            patch.object(detector, "Esp32MjpegCapture", LocalEsp32Capture):
        try:
            for key in detector.get_source_keys():
                if not detector.start_source_worker(key):
                    raise RuntimeError(f"Worker failed to start: {key}")
            deadline = time.monotonic() + 30
            while not all(status["frame_ready"] for status in detector.get_source_status().values()):
                if time.monotonic() > deadline:
                    raise RuntimeError("Not all four sources produced inference frames")
                time.sleep(0.05)
            counts = {key: status["frame_sequence"] for key, status in detector.get_source_status().items()}
            started = time.monotonic()
            time.sleep(3)
            elapsed = time.monotonic() - started
            statuses = detector.get_source_status()
            channels = {}
            concurrent_clients = []
            barrier = threading.Barrier(4, action=lambda: concurrent_clients.append(detector.active_connections))
            def check_stream(key):
                with app.test_client() as client:
                    response = client.get(f"/stream/video_feed/{key}", buffered=False)
                    try:
                        chunk = next(response.response)
                        if response.status_code != 200 or b"Content-Type: image/jpeg" not in chunk:
                            raise RuntimeError(f"MJPEG route did not provide an image: {key}")
                        barrier.wait(timeout=10)
                        return response.status_code
                    finally:
                        response.close()
            with ThreadPoolExecutor(max_workers=4) as clients:
                codes = dict(zip(statuses, clients.map(check_stream, statuses)))
            health_response = app.test_client().get("/stream/health")
            health = health_response.get_json()
            if not all(health.get(key) is True for key in ("processReady", "aiReady", "ready")):
                raise RuntimeError("Actual GPU initialization and public readiness state disagree")
            if health["ai"]["device"] != "cuda:0":
                raise RuntimeError("Health does not report the actual CUDA model device")
            for key, status in statuses.items():
                current = detector.get_source_status()[key]
                channels[key] = {"pipeline_fps": (status["frame_sequence"] - counts[key]) / elapsed,
                                 "last_processing_ms": status["last_processing_ms"],
                                 "last_frame_age_ms": (time.time() - current["last_frame_at"]) * 1000,
                                 "mjpeg_http": codes[key]}
            report = {"scenario": "three real local videos + local-video simulated ESP32; external IO blocked",
                      "model_constructor_calls": constructor.call_count, "channels": channels,
                      "health": {key: health[key] for key in ("processReady", "aiReady", "ready")},
                      "concurrent_mjpeg_clients": max(concurrent_clients),
                      "device": detector.get_ai_runtime_status()["device"],
                      "allocated_mib": torch.cuda.memory_allocated() / 2**20,
                      "reserved_mib": torch.cuda.memory_reserved() / 2**20}
        finally:
            detector.shutdown_ai_runtime()
    report.update(allocated_after_release_mib=torch.cuda.memory_allocated() / 2**20,
                  reserved_after_release_mib=torch.cuda.memory_reserved() / 2**20,
                  workers_stopped=all(not status["running"] and not status["stopping"]
                                      for status in detector.get_source_status().values()))
    if constructor.call_count != 1:
        raise RuntimeError("The four sources loaded more than one model")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
