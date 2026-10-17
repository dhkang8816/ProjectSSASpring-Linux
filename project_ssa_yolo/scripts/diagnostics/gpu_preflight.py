"""Explicit, offline GPU/model check for an owner-trusted local checkpoint."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--sha256", required=True, help="owner-verified checkpoint fingerprint")
    parser.add_argument("--video", type=Path, help="use the first frame as a single test image")
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    model_path = args.model.resolve(strict=True)
    with model_path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != args.sha256.lower():
        raise RuntimeError("Checkpoint hash mismatch; model loading was refused")
    os.environ["YOLO_OFFLINE"] = "true"
    os.environ["YOLO_AUTOINSTALL"] = "false"
    def block_network(event, _args):
        if event == "socket.connect":
            raise PermissionError("Network access is disabled in the offline GPU preflight")
    sys.addaudithook(block_network)

    import cv2
    import numpy as np
    import torch
    import torchvision
    import ultralytics
    ultralytics.utils.SETTINGS.update({"sync": False})
    from ultralytics import YOLO

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from apps.services.inference_device import resolve_device
    device = resolve_device(args.device, torch)
    if args.video:
        capture = cv2.VideoCapture(str(args.video.resolve(strict=True)))
        try:
            success, image = capture.read()
        finally:
            capture.release()
        if not success:
            raise RuntimeError("Test video could not supply a single image")
        input_kind = "first local video frame"
    else:
        image = np.zeros((640, 640, 3), dtype=np.uint8)
        input_kind = "synthetic black image"

    if device.startswith("cuda:"):
        torch.cuda.reset_peak_memory_stats(device)
    model = YOLO(str(model_path))
    model.to(device)
    expected = {"dog", "cat", "blue_alien", "blue_shark", "pink_dragon", "tiger"}
    if set(model.names.values()) != expected:
        raise RuntimeError("Checkpoint classes differ from the project's six event classes")
    model.predict(image, device=device, verbose=False)
    elapsed = []
    for _ in range(10):
        start = time.perf_counter()
        results = model.predict(image, device=device, verbose=False)
        if device.startswith("cuda:"):
            torch.cuda.synchronize(device)
        elapsed.append((time.perf_counter() - start) * 1000)
    actual = str(next(model.model.parameters()).device)
    if actual != device:
        raise RuntimeError("Model device differs from the requested device")
    report = {
        "python": sys.version.split()[0], "torch": torch.__version__,
        "torchvision": torchvision.__version__, "torch_cuda": torch.version.cuda,
        "ultralytics": ultralytics.__version__, "opencv": cv2.__version__,
        "numpy": np.__version__, "device": actual, "model_sha256": digest,
        "checkpoint_ultralytics": model.ckpt.get("version"),
        "original_torch_version": model.ckpt.get("torch_version", "not recorded"),
        "model_yaml": Path(str(model.model.yaml.get("yaml_file", "unknown"))).name,
        "parameters": sum(parameter.numel() for parameter in model.model.parameters()),
        "classes": model.names, "input": input_kind,
        "mean_predict_ms": sum(elapsed) / len(elapsed),
        "detections": len(results[0].boxes),
    }
    if device.startswith("cuda:"):
        properties = torch.cuda.get_device_properties(device)
        report.update(gpu=properties.name, gpu_total_mib=properties.total_memory // 2**20,
                      peak_allocated_mib=torch.cuda.max_memory_allocated(device) / 2**20,
                      reserved_mib=torch.cuda.memory_reserved(device) / 2**20)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
