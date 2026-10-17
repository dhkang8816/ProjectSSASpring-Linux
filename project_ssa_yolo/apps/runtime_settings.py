"""Non-secret settings: OS data directories and explicitly configured assets."""

import os
import re
from pathlib import Path, PureWindowsPath

from apps.environment import PROJECT_ROOT, REPOSITORY_ROOT, load_project_environment


load_project_environment()


def _text(name, default):
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _float(name, default, minimum=0.0):
    try:
        value = float(_text(name, str(default)))
    except ValueError:
        return default
    return value if value >= minimum else default


def _int(name, default, minimum=0):
    try:
        value = int(_text(name, str(default)))
    except ValueError:
        return default
    return value if value >= minimum else default


def _bool(name, default=False):
    value = _text(name, "true" if default else "false").lower()
    return value in {"1", "true", "yes", "on"}


SPRING_HOST = _text("SSA_SPRING_HOST", "http://localhost:8080/project_ssa_spring-0.0.1-SNAPSHOT").rstrip("/")
ESP32_STREAM_URL = _text("SSA_ESP32_STREAM_URL", "http://192.168.0.100:80/stream")
ESP32_COM_PORT = _text("SSA_ESP32_COM_PORT", "COM6" if os.name == "nt" else "")

# Battery telemetry is produced by the existing ESP32 sensor polling command;
# it never opens another serial connection.  The values below match the ESP32-S3
# board circuit: GPIO2 receives VBAT through a 40.2k / 10k divider, so the
# physical VBAT restoration ratio is (40.2 + 10) / 10 = 5.02.  The 1.0V raw
# scale preserves the board vendor's validated formula:
# raw / 4095 * 5.02 * 0.96.
BATTERY_ENABLED = _bool("SSA_BATTERY_ENABLED", True)
BATTERY_SOURCE_KEY = _text("SSA_BATTERY_SOURCE_KEY", "esp32")
if BATTERY_SOURCE_KEY not in {"video_1", "video_2", "video_3", "esp32"}:
    BATTERY_SOURCE_KEY = "esp32"
BATTERY_ADC_PIN = _int("SSA_BATTERY_ADC_PIN", 2, minimum=0)
BATTERY_ADC_REFERENCE_VOLTAGE = _float("SSA_BATTERY_ADC_REFERENCE_VOLTAGE", 1.0, minimum=0.1)
BATTERY_MIN_VOLTAGE = _float("SSA_BATTERY_MIN_VOLTAGE", 3.0, minimum=0.1)
BATTERY_MAX_VOLTAGE = _float("SSA_BATTERY_MAX_VOLTAGE", 4.25, minimum=0.1)
if BATTERY_MAX_VOLTAGE <= BATTERY_MIN_VOLTAGE:
    BATTERY_MIN_VOLTAGE, BATTERY_MAX_VOLTAGE = 3.0, 4.25
BATTERY_DIVIDER_RATIO = _float("SSA_BATTERY_DIVIDER_RATIO", 5.02, minimum=0.01)
BATTERY_CALIBRATION = _float("SSA_BATTERY_CALIBRATION", 0.96, minimum=0.01)
BATTERY_SAMPLE_COUNT = _int("SSA_BATTERY_SAMPLE_COUNT", 8, minimum=1)
BATTERY_LOW_PERCENT = _float("SSA_BATTERY_LOW_PERCENT", 25.0, minimum=0.0)
BATTERY_CRITICAL_PERCENT = _float("SSA_BATTERY_CRITICAL_PERCENT", 10.0, minimum=0.0)
if BATTERY_CRITICAL_PERCENT > BATTERY_LOW_PERCENT:
    BATTERY_CRITICAL_PERCENT, BATTERY_LOW_PERCENT = 10.0, 25.0
BATTERY_MOCK_ENABLED = _bool("SSA_BATTERY_MOCK_ENABLED", False)
BATTERY_MOCK_PERCENT = min(100.0, _float("SSA_BATTERY_MOCK_PERCENT", 80.0, minimum=0.0))
BATTERY_DEBUG = _bool("SSA_BATTERY_DEBUG", False)
BATTERY_DEBUG_INTERVAL_SECONDS = _float("SSA_BATTERY_DEBUG_INTERVAL_SECONDS", 30.0, minimum=1.0)
BUZZER_STARTUP_SOUND_ENABLED = _bool("SSA_BUZZER_STARTUP_SOUND_ENABLED", True)
BUZZER_SHUTDOWN_SOUND_ENABLED = _bool("SSA_BUZZER_SHUTDOWN_SOUND_ENABLED", True)
BUZZER_SHUTDOWN_SOUND_WAIT_SECONDS = _float(
    "SSA_BUZZER_SHUTDOWN_SOUND_WAIT_SECONDS", 5.0, minimum=0.1
)
YOLO_MODEL_PATH = _text("SSA_YOLO_MODEL_PATH", "")
YOLO_DEVICE = _text("SSA_YOLO_DEVICE", "cuda:0")
OPTIONAL_IO_ENABLED = _bool("SSA_OPTIONAL_IO_ENABLED", True)
VIDEO_PATHS = {
    "video_1": _text("SSA_VIDEO_1_PATH", ""),
    "video_2": _text("SSA_VIDEO_2_PATH", ""),
    "video_3": _text("SSA_VIDEO_3_PATH", ""),
}

# All detector workers are built from this one registry.  Adding a source only
# requires a setting here; routes and worker management do not hard-code keys.
VIDEO_SOURCES = {
    key: {"mode": "video", "uri": path}
    for key, path in VIDEO_PATHS.items()
}
VIDEO_SOURCES["esp32"] = {"mode": "esp32", "uri": ESP32_STREAM_URL}
DEFAULT_VIDEO_SOURCE_KEY = _text("SSA_DEFAULT_VIDEO_SOURCE", "video_1")
if DEFAULT_VIDEO_SOURCE_KEY not in VIDEO_SOURCES:
    DEFAULT_VIDEO_SOURCE_KEY = "video_1"

UPLOAD_ROOT = _text("SSA_UPLOAD_ROOT", "C:/upload" if os.name == "nt" else "/var/lib/project-ssa/uploads")


class RuntimePathError(ValueError):
    """A local path is unusable; messages identify settings without their values."""


def filesystem_path(name, value, *, absolute=False):
    """Resolve relative local paths against the repository, never process cwd."""
    value = str(value or "").strip()
    if not value:
        raise RuntimePathError(f"{name} must be configured")
    if "://" in value or (os.name != "nt" and PureWindowsPath(value).drive):
        raise RuntimePathError(f"{name} must be a file-system path for this OS")
    try:
        path = Path(value).expanduser()
        if absolute and not path.is_absolute():
            raise RuntimePathError(f"{name} must be an absolute file-system path")
        if not path.is_absolute():
            path = REPOSITORY_ROOT / path
        return path.resolve()
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, RuntimePathError):
            raise
        raise RuntimePathError(f"{name} is not a valid file-system path") from None


def readable_file(name, value):
    """Check before OpenCV/Ultralytics can interpret a missing file as a source."""
    path = filesystem_path(name, value)
    try:
        if not path.is_file() or not os.access(path, os.R_OK):
            raise RuntimePathError(f"{name} must reference an existing readable file")
    except OSError:
        raise RuntimePathError(f"{name} cannot be accessed") from None
    return path


def upload_directory(folder_name, *, create=False):
    """Resolve the shared store; only actual snapshot writes create directories."""
    if folder_name not in {"detection", "dangerlog"}:
        raise RuntimePathError("Unsupported snapshot category")
    root = filesystem_path("SSA_UPLOAD_ROOT", UPLOAD_ROOT, absolute=True)
    directory = root / folder_name
    try:
        # The categories are fixed, but an existing symlink must not escape root.
        directory.resolve().relative_to(root)
        if create:
            directory.mkdir(parents=True, exist_ok=True)
            if not directory.is_dir() or not os.access(directory, os.W_OK | os.X_OK):
                raise RuntimePathError("SSA_UPLOAD_ROOT must allow snapshot writes")
    except (OSError, ValueError):
        raise RuntimePathError("SSA_UPLOAD_ROOT cannot provide the snapshot directory") from None
    return directory


def validate_serial_port(value):
    """Reject stale Windows COM names on Linux before invoking mpremote."""
    value = str(value or "").strip()
    if not value:
        raise RuntimePathError("SSA_ESP32_COM_PORT must be configured")
    if os.name == "nt":
        return value
    if re.fullmatch(r"COM\d+", value, re.IGNORECASE):
        raise RuntimePathError("SSA_ESP32_COM_PORT must identify a serial device for this OS")
    path = filesystem_path("SSA_ESP32_COM_PORT", value, absolute=True)
    try:
        if not path.is_char_device() or not os.access(path, os.R_OK | os.W_OK):
            raise RuntimePathError("SSA_ESP32_COM_PORT must reference an accessible serial device")
    except OSError:
        raise RuntimePathError("SSA_ESP32_COM_PORT cannot be accessed") from None
    return str(path)

YOLO_CONFIDENCE = _float("SSA_YOLO_CONFIDENCE", 0.50, minimum=0.0)
ANIMAL_UNDER_TARGET_SECONDS = _float("SSA_ANIMAL_UNDER_TARGET_SECONDS", 10.0, minimum=0.0)
ANIMAL_RECOVERY_SECONDS = _float("SSA_ANIMAL_RECOVERY_SECONDS", 2.5, minimum=0.0)
ALARM_COOLDOWN_SECONDS = _float("SSA_ALARM_COOLDOWN_SECONDS", 10.0, minimum=0.0)
ANIMAL_TARGET_REFRESH_SECONDS = _float("SSA_ANIMAL_TARGET_REFRESH_SECONDS", 15.0, minimum=1.0)
METADATA_REQUEST_TIMEOUT_SECONDS = _float("SSA_METADATA_REQUEST_TIMEOUT_SECONDS", 1.0, minimum=0.1)
EVENT_REQUEST_TIMEOUT_SECONDS = _float("SSA_EVENT_REQUEST_TIMEOUT_SECONDS", 3.0, minimum=0.1)
MAPPING_REQUEST_TIMEOUT_SECONDS = _float("SSA_MAPPING_REQUEST_TIMEOUT_SECONDS", 1.0, minimum=0.1)
# ESP32-CAM exposes an HTTP multipart MJPEG stream.  It is read with requests
# rather than OpenCV/FFmpeg because that firmware stream can take longer than
# FFmpeg's short open/read timeout and does not reliably support its decoder.
ESP32_HTTP_CONNECT_TIMEOUT_SECONDS = _float(
    "SSA_ESP32_HTTP_CONNECT_TIMEOUT_SECONDS", 5.0, minimum=0.1
)
ESP32_HTTP_READ_TIMEOUT_SECONDS = _float(
    "SSA_ESP32_HTTP_READ_TIMEOUT_SECONDS", 2.0, minimum=0.1
)
ESP32_MJPEG_BUFFER_MAX_BYTES = _int(
    "SSA_ESP32_MJPEG_BUFFER_MAX_BYTES", 4 * 1024 * 1024, minimum=1024
)
ESP32_RECONNECT_INITIAL_SECONDS = _float(
    "SSA_ESP32_RECONNECT_INITIAL_SECONDS", 1.0, minimum=0.05
)
ESP32_RECONNECT_MAX_SECONDS = _float(
    "SSA_ESP32_RECONNECT_MAX_SECONDS", 5.0, minimum=0.05
)
if ESP32_RECONNECT_MAX_SECONDS < ESP32_RECONNECT_INITIAL_SECONDS:
    ESP32_RECONNECT_INITIAL_SECONDS, ESP32_RECONNECT_MAX_SECONDS = 1.0, 5.0
ESP32_RECEIVER_JOIN_TIMEOUT_SECONDS = _float("SSA_ESP32_RECEIVER_JOIN_TIMEOUT_SECONDS", 1.5, minimum=0.1)
SOURCE_WORKER_STOP_TIMEOUT_SECONDS = _float("SSA_SOURCE_WORKER_STOP_TIMEOUT_SECONDS", 5.0, minimum=0.1)
SOURCE_WORKER_FRAME_INTERVAL_SECONDS = _float("SSA_SOURCE_WORKER_FRAME_INTERVAL_SECONDS", 0.03, minimum=0.0)
SOURCE_WORKER_RETRY_SECONDS = _float("SSA_SOURCE_WORKER_RETRY_SECONDS", 0.5, minimum=0.05)
AUTO_START_DETECTION_WORKERS = _bool("SSA_AUTO_START_DETECTION_WORKERS", False)
