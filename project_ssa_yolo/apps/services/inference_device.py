"""Explicit inference device selection; CUDA requests never fall back to CPU."""

import re


def resolve_device(requested, torch):
    value = str(requested).strip().lower()
    if value == "cpu":
        return "cpu"
    match = re.fullmatch(r"(?:cuda(?::(\d+))?|(\d+))", value)
    if not match:
        raise RuntimeError("SSA_YOLO_DEVICE must be cpu, cuda, cuda:N, or a GPU index")
    index = int(match.group(1) or match.group(2) or 0)
    if not torch.cuda.is_available():
        raise RuntimeError("SSA_YOLO_DEVICE requests CUDA, but CUDA is unavailable; check the WSL GPU/driver and PyTorch CUDA build")
    if index >= torch.cuda.device_count():
        raise RuntimeError("SSA_YOLO_DEVICE references an unavailable CUDA GPU index")
    # Exercise the runtime instead of treating an NVML listing as CUDA readiness.
    device = f"cuda:{index}"
    sample = torch.ones((8, 8), device=device)
    if not bool(torch.all(sample @ sample == 8).item()):
        raise RuntimeError("CUDA tensor validation failed")
    torch.cuda.synchronize(index)
    return device
