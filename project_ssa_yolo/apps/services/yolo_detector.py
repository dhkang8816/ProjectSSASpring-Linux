"""Thread-safe multi-source YOLO detector.

Each configured source owns one capture/processing worker and one latest-result
buffer. A single Ultralytics model is shared behind ``_model_inference_lock``:
Ultralytics/PyTorch inference is not assumed to be safe for concurrent calls,
and loading the same weights once per source would multiply CPU/GPU memory.
"""

import atexit
import threading
import time
from datetime import datetime

import cv2
from ultralytics import YOLO

from apps import runtime_settings
from apps.services.esp32_mjpeg import Esp32MjpegCapture
from apps.services import oracle_service
from apps.services.buzzer_helper import trigger_animal_sound, trigger_danger_sound


YOLO_TO_CODE = {
    "dog": "0",
    "cat": "1",
    "blue_alien": "2",
    "blue_shark": "3",
    "pink_dragon": "4",
    "tiger": "5",
}
ANIMAL_LABELS = ("dog", "cat")
DANGER_LABELS = ("blue_alien", "blue_shark", "pink_dragon", "tiger")

ANIMAL_NAME_MAP = {}
TARGET_ANIMALS = {"0": 2, "1": 1}
ANIMAL_UNDER_TARGET_SECONDS = runtime_settings.ANIMAL_UNDER_TARGET_SECONDS
ALARM_COOLDOWN = runtime_settings.ALARM_COOLDOWN_SECONDS
program_start_time = None

# Legacy single-source values remain available for existing callers. They are
# mirrors of the selected default source only; new code must use the accessors.
current_frame = None
current_boxes = []
active_connections = 0
is_running = False
current_mode = "video"
current_source_path = runtime_settings.VIDEO_PATHS["video_1"]
source_changed = False

_model = None
_model_inference_lock = threading.RLock()
_metadata_lock = threading.RLock()
_metadata_initialized = False
_last_target_refresh_time = 0.0
_target_refresh_in_progress = False
_animal_policy_version = None
_event_state_lock = threading.RLock()
_manager_lock = threading.RLock()
_legacy_state_lock = threading.Lock()

# Per-source timers ensure an alert on one camera never suppresses another.
under_target_start_time = {}
recovery_start_time = {}
last_alarm_time = {}


def init_ai_metadata_from_oracle():
    """Load common-code labels, targets, and the runtime policy once."""
    global ANIMAL_NAME_MAP, TARGET_ANIMALS, program_start_time, _metadata_initialized
    global _last_target_refresh_time

    with _metadata_lock:
        if _metadata_initialized:
            return
        program_start_time = time.time()
        try:
            db_code_map = oracle_service.fetch_code_map()
            raw_targets = oracle_service.fetch_target_counts()
            TARGET_ANIMALS = {str(key): int(value) for key, value in raw_targets.items()}
            ANIMAL_NAME_MAP = {
                label: db_code_map[code]
                for label, code in YOLO_TO_CODE.items()
                if code in db_code_map
            }
            alert_policy = oracle_service.fetch_alert_policy()
            if alert_policy is not None:
                _apply_animal_shortage_policy(alert_policy)
            print(f"[YOLO metadata ready] targets={TARGET_ANIMALS}")
        except Exception as error:
            print(f"[YOLO metadata fallback] {error}")
        finally:
            _last_target_refresh_time = time.monotonic()
            _metadata_initialized = True


def refresh_animal_targets_if_due():
    """Refresh target counts and alert policy without blocking inference."""
    global TARGET_ANIMALS, _last_target_refresh_time, _target_refresh_in_progress

    if not _metadata_initialized:
        return

    now = time.monotonic()
    with _metadata_lock:
        if (
            _target_refresh_in_progress
            or now - _last_target_refresh_time < runtime_settings.ANIMAL_TARGET_REFRESH_SECONDS
        ):
            return
        _target_refresh_in_progress = True

    def refresh():
        global TARGET_ANIMALS, _last_target_refresh_time, _target_refresh_in_progress
        try:
            raw_targets = oracle_service.fetch_target_counts()
            refreshed_targets = {
                str(key): int(value) for key, value in raw_targets.items()
            }
            alert_policy = oracle_service.fetch_alert_policy()
            with _metadata_lock:
                TARGET_ANIMALS = refreshed_targets
            if alert_policy is not None:
                _apply_animal_shortage_policy(alert_policy)
        except Exception as error:
            # Retain the last known protected-animal counts during a transient
            # Spring/Oracle outage rather than changing shortage behavior.
            print(f"[YOLO target refresh retained cache] {error}")
        finally:
            with _metadata_lock:
                _last_target_refresh_time = time.monotonic()
                _target_refresh_in_progress = False

    threading.Thread(
        target=refresh,
        name="yolo-animal-target-refresh",
        daemon=True,
    ).start()


def _apply_animal_shortage_policy(policy):
    """Install a fetched duration and restart only pending shortage timers."""
    global ANIMAL_UNDER_TARGET_SECONDS, _animal_policy_version

    seconds = float(policy["underTargetSeconds"])
    version = str(policy["version"])
    if not 1.0 <= seconds <= 3600.0 or not version:
        raise ValueError("invalid animal shortage policy")

    with _metadata_lock:
        changed = (
            seconds != ANIMAL_UNDER_TARGET_SECONDS
            or version != _animal_policy_version
        )
        if not changed:
            return False
        ANIMAL_UNDER_TARGET_SECONDS = seconds
        _animal_policy_version = version

    # A timer that began under the old duration must not fire under the new
    # rule. Cooldowns remain intact because only the pending shortage window
    # changes.
    with _event_state_lock:
        for source_key, under_target in under_target_start_time.items():
            for label in ANIMAL_LABELS:
                under_target[YOLO_TO_CODE[label]] = None
        for source_key, recovery in recovery_start_time.items():
            for label in ANIMAL_LABELS:
                recovery[YOLO_TO_CODE[label]] = None

    print(
        "[YOLO alert policy applied] "
        f"under_target_seconds={ANIMAL_UNDER_TARGET_SECONDS}, version={version}"
    )
    return True


def _event_state_for(source_key):
    """Return the isolated cooldown/timer maps for one video source."""
    source_key = str(source_key)
    under_target = under_target_start_time.setdefault(source_key, {"0": None, "1": None})
    recovery = recovery_start_time.setdefault(source_key, {"0": None, "1": None})
    cooldown = last_alarm_time.setdefault(
        source_key, {code: 0.0 for code in YOLO_TO_CODE.values()}
    )
    return under_target, recovery, cooldown


def _notification_metadata(event_type, label, boxes):
    """Use inference metadata already produced for this frame; never re-run YOLO."""
    confidence = None
    for box in boxes or ():
        if len(box) >= 6 and box[4] == label:
            value = box[5]
            confidence = value if confidence is None else max(confidence, value)
    return {
        "event_type": event_type,
        "object_label": label,
        "confidence": confidence,
        "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def process_animal_detection_logic(detected_names, frame, source_key=None, boxes=None):
    """Apply animal-count policy with timers isolated by source key."""
    refresh_animal_targets_if_due()
    source_key = source_key or get_default_source_key()
    current_time = time.time()
    pending_reports = []

    with _event_state_lock:
        under_target, recovery, cooldown = _event_state_for(source_key)

        # No recognised shelter animal in a frame means the camera/YOLO result
        # cannot prove a shortage.  Once at least one dog or cat is recognised,
        # compare every protected animal type: a detected dog with no detected
        # cat is a valid cat-shortage condition.
        if not any(label in ANIMAL_LABELS for label in detected_names):
            for label in ANIMAL_LABELS:
                code_id = YOLO_TO_CODE[label]
                under_target[code_id] = None
                recovery[code_id] = None
            return

        for label in ANIMAL_LABELS:
            code_id = YOLO_TO_CODE[label]
            target_count = int(TARGET_ANIMALS.get(code_id, 0))
            current_count = detected_names.count(label)

            if current_count < target_count:
                recovery[code_id] = None
                if under_target.get(code_id) is None:
                    under_target[code_id] = current_time
                elif (
                    current_time - under_target[code_id]
                    >= ANIMAL_UNDER_TARGET_SECONDS
                    and current_time - cooldown.get(code_id, 0.0) >= ALARM_COOLDOWN
                ):
                    cooldown[code_id] = current_time
                    display_name = ANIMAL_NAME_MAP.get(label, label)
                    pending_reports.append((code_id, current_count, display_name, label))
            elif under_target.get(code_id) is not None:
                if recovery.get(code_id) is None:
                    recovery[code_id] = current_time
                elif current_time - recovery[code_id] >= runtime_settings.ANIMAL_RECOVERY_SECONDS:
                    under_target[code_id] = None
                    recovery[code_id] = None

    # oracle_service queues HTTP/snapshot work, so do not hold the event lock.
    for code_id, current_count, display_name, label in pending_reports:
        oracle_service.send_log_to_oracle(
            animal_type=code_id,
            detect_count=current_count,
            reason=(
                f"AI 관제 시스템 실시간 분석 - {display_name} 보유 마리수 기준치 미달 현상 지속"
            ),
            frame=frame,
            source_key=source_key,
            notification=_notification_metadata("animal", label, boxes),
        )
        trigger_animal_sound()


def process_danger_detection_logic(detected_names, frame, source_key=None, boxes=None):
    """Apply danger-object cooldown separately for every video source."""
    source_key = source_key or get_default_source_key()
    current_time = time.time()
    danger_reports = []

    with _event_state_lock:
        _, _, cooldown = _event_state_for(source_key)
        for label in DANGER_LABELS:
            if label not in detected_names:
                continue
            code_id = YOLO_TO_CODE[label]
            if current_time - cooldown.get(code_id, 0.0) < ALARM_COOLDOWN:
                continue
            cooldown[code_id] = current_time
            danger_reports.append((code_id, ANIMAL_NAME_MAP.get(label, label), label))

    for code_id, display_name, label in danger_reports:
        print(f"[DANGER:{source_key}] {display_name} detected")
        oracle_service.send_danger_log_to_oracle(
            danger_type=code_id,
            frame=frame,
            source_key=source_key,
            notification=_notification_metadata("danger", label, boxes),
        )
        trigger_danger_sound()


def process_detection_events(detected_names, frame, source_key=None, boxes=None):
    """Run all event policies for one source-specific inference result."""
    process_animal_detection_logic(detected_names, frame, source_key, boxes)
    process_danger_detection_logic(detected_names, frame, source_key, boxes)


def _run_inference(frame):
    """Return one annotated result while safely sharing one model instance."""
    global _model
    # One model + lock protects mutable PyTorch/Ultralytics inference state and
    # avoids loading the same weights once per source.
    with _model_inference_lock:
        if _model is None:
            model_path = runtime_settings.readable_file("SSA_YOLO_MODEL_PATH", runtime_settings.YOLO_MODEL_PATH)
            _model = YOLO(str(model_path))
            print("[YOLO] shared model loaded")
        results = _model(frame, conf=runtime_settings.YOLO_CONFIDENCE, verbose=False)

    detected_names = []
    boxes_for_client = []
    if not results:
        return frame, detected_names, boxes_for_client

    result = results[0]
    boxes = result.boxes
    if boxes is not None:
        names = result.names
        for box in boxes:
            confidence = float(box.conf.item())
            if confidence < runtime_settings.YOLO_CONFIDENCE:
                continue
            coordinates = box.xyxy.tolist()[0]
            label = names[int(box.cls.item())]
            detected_names.append(label)
            boxes_for_client.append([
                coordinates[0],
                coordinates[1],
                coordinates[2] - coordinates[0],
                coordinates[3] - coordinates[1],
                label,
                confidence,
            ])
    return result.plot(), detected_names, boxes_for_client


class SourceWorker:
    """Own one VideoCapture and the latest completed YOLO result for a source."""

    def __init__(self, source_key, source_config):
        self.source_key = source_key
        self.mode = source_config["mode"]
        self.uri = source_config["uri"]
        self.stop_event = threading.Event()
        self.frame_lock = threading.RLock()
        self.capture_lock = threading.Lock()
        self.thread = None
        self.capture = None
        self.latest_frame = None
        self.latest_boxes = []
        self.last_error = None
        self.last_frame_at = None
        self.frame_sequence = 0
        self._esp32_retry_delay = runtime_settings.ESP32_RECONNECT_INITIAL_SECONDS

    def start(self):
        with self.capture_lock:
            if self.thread is not None and self.thread.is_alive():
                return False
            try:
                runtime_settings.readable_file("SSA_YOLO_MODEL_PATH", runtime_settings.YOLO_MODEL_PATH)
                if self.mode != "esp32":
                    runtime_settings.readable_file(f"SSA_{self.source_key.upper()}_PATH", self.uri)
            except runtime_settings.RuntimePathError as error:
                self._set_error(error)
                print(f"[YOLO:{self.source_key}] configuration error: {error}")
                return False
            self.stop_event.clear()
            self.thread = threading.Thread(
                target=self._run,
                name=f"yolo-source-{self.source_key}",
                daemon=True,
            )
            self.thread.start()
            print(f"[SourceWorker {self.source_key}] started")
            return True

    def stop(self, join_timeout=None):
        """Request shutdown; only ``_run`` is allowed to release VideoCapture."""
        self.stop_event.set()
        print(f"[SourceWorker {self.source_key}] stop requested")
        thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            timeout = join_timeout or runtime_settings.SOURCE_WORKER_STOP_TIMEOUT_SECONDS
            if self.mode == "esp32":
                # An HTTP connect can still be in progress when OFF is
                # pressed.  Give that one bounded request enough time to
                # return, rather than incorrectly reporting a failed stop.
                timeout = max(
                    timeout,
                    runtime_settings.ESP32_HTTP_CONNECT_TIMEOUT_SECONDS + 0.5,
                )
            thread.join(
                timeout
            )
        with self.frame_lock:
            self.latest_frame = None
            self.latest_boxes = []
            self.last_frame_at = None
        stopped = thread is None or not thread.is_alive()
        if stopped:
            print(f"[SourceWorker {self.source_key}] stopped")
        return stopped

    def snapshot_frame(self):
        with self.frame_lock:
            return None if self.latest_frame is None else self.latest_frame.copy()

    def snapshot_boxes(self):
        with self.frame_lock:
            return list(self.latest_boxes)

    def status(self):
        thread = self.thread
        thread_alive = thread is not None and thread.is_alive()
        stopping = thread_alive and self.stop_event.is_set()
        with self.frame_lock:
            return {
                "running": thread_alive and not stopping,
                "stopping": stopping,
                "stopped": not thread_alive,
                "frame_ready": self.latest_frame is not None,
                "last_frame_at": self.last_frame_at,
                "frame_sequence": self.frame_sequence,
                "last_error": self.last_error,
            }

    def _set_error(self, error):
        with self.frame_lock:
            self.last_error = str(error)

    def _open_capture(self):
        if self.mode != "esp32":
            setting_name = f"SSA_{self.source_key.upper()}_PATH"
            video_path = runtime_settings.readable_file(setting_name, self.uri)
            capture = cv2.VideoCapture(str(video_path))
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return capture

        capture = Esp32MjpegCapture(
            self.uri,
            connect_timeout_seconds=runtime_settings.ESP32_HTTP_CONNECT_TIMEOUT_SECONDS,
            read_timeout_seconds=runtime_settings.ESP32_HTTP_READ_TIMEOUT_SECONDS,
            max_buffer_bytes=runtime_settings.ESP32_MJPEG_BUFFER_MAX_BYTES,
        )
        capture.open()
        return capture

    def _next_retry_delay(self):
        if self.mode != "esp32":
            return runtime_settings.SOURCE_WORKER_RETRY_SECONDS
        delay = self._esp32_retry_delay
        self._esp32_retry_delay = min(
            runtime_settings.ESP32_RECONNECT_MAX_SECONDS,
            max(
                runtime_settings.ESP32_RECONNECT_INITIAL_SECONDS,
                self._esp32_retry_delay * 2,
            ),
        )
        return delay

    def _reset_retry_delay(self):
        if self.mode == "esp32":
            self._esp32_retry_delay = runtime_settings.ESP32_RECONNECT_INITIAL_SECONDS

    def _publish(self, frame, boxes):
        global current_frame, current_boxes
        with self.frame_lock:
            self.latest_frame = frame
            self.latest_boxes = boxes
            self.last_frame_at = time.time()
            self.last_error = None
            self.frame_sequence += 1
        if self.source_key == get_default_source_key():
            with _legacy_state_lock:
                current_frame = frame
                current_boxes = list(boxes)

    def _run(self):
        init_ai_metadata_from_oracle()
        while not self.stop_event.is_set():
            capture = None
            retry_after_release = False
            try:
                capture = self._open_capture()
                with self.capture_lock:
                    if self.stop_event.is_set():
                        break
                    self.capture = capture

                if not capture.isOpened():
                    self._set_error(
                        getattr(capture, "last_error", None)
                        or "VideoCapture could not be opened"
                    )
                    retry_after_release = True
                    continue

                while not self.stop_event.is_set():
                    success, frame = capture.read()
                    if not success:
                        self._set_error(
                            getattr(capture, "last_error", None)
                            or "VideoCapture frame read failed"
                        )
                        if self.mode == "video":
                            # Loop valid files, but do not spin on a capture that
                            # opened successfully yet cannot decode any frame.
                            if capture.get(cv2.CAP_PROP_FRAME_COUNT) > 0:
                                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                                self.stop_event.wait(runtime_settings.SOURCE_WORKER_FRAME_INTERVAL_SECONDS)
                                continue
                        retry_after_release = True
                        break
                    self._reset_retry_delay()
                    try:
                        annotated_frame, detected_names, boxes = _run_inference(frame)
                        if self.stop_event.is_set():
                            break
                        process_detection_events(
                            detected_names,
                            annotated_frame,
                            self.source_key,
                            boxes,
                        )
                        if self.stop_event.is_set():
                            break
                        self._publish(annotated_frame, boxes)
                    except Exception as error:
                        self._set_error(error)
                        print(f"[YOLO:{self.source_key}] inference error: {error}")
                        self.stop_event.wait(runtime_settings.SOURCE_WORKER_RETRY_SECONDS)
                    else:
                        # No queue is retained: each source keeps only its newest
                        # completed result, prioritising low latency over history.
                        self.stop_event.wait(runtime_settings.SOURCE_WORKER_FRAME_INTERVAL_SECONDS)
            except Exception as error:
                self._set_error(error)
                print(f"[YOLO:{self.source_key}] worker error: {error}")
                retry_after_release = True
            finally:
                if capture is not None:
                    # This worker is the sole owner of its decoder. Never call
                    # release() from HTTP/control threads while read() may run.
                    capture.release()
                    print(f"[SourceWorker {self.source_key}] capture released")
                with self.capture_lock:
                    if self.capture is capture:
                        self.capture = None
            if retry_after_release:
                self.stop_event.wait(self._next_retry_delay())


_workers = {
    source_key: SourceWorker(source_key, source_config)
    for source_key, source_config in runtime_settings.VIDEO_SOURCES.items()
}
_default_source_key = runtime_settings.DEFAULT_VIDEO_SOURCE_KEY


def is_known_source(source_key):
    return source_key in _workers


def get_source_keys():
    return tuple(_workers.keys())


def get_default_source_key():
    with _manager_lock:
        return _default_source_key


def start_source_worker(source_key):
    global is_running
    worker = _workers.get(source_key)
    if worker is None:
        return False
    worker.start()
    is_running = any(item.status()["running"] for item in _workers.values())
    return worker.status()["running"]


def stop_source_worker(source_key):
    global current_frame, current_boxes, is_running
    worker = _workers.get(source_key)
    if worker is None:
        return False
    stopped = worker.stop()
    if source_key == get_default_source_key():
        with _legacy_state_lock:
            current_frame = None
            current_boxes = []
    is_running = any(status["running"] for status in get_source_status().values())
    return stopped


def start_all_workers():
    global is_running
    is_running = True
    for source_key in get_source_keys():
        start_source_worker(source_key)
    return get_source_status()


def stop_all_workers():
    global is_running, current_frame, current_boxes
    is_running = False
    for worker in tuple(_workers.values()):
        worker.stop()
    with _legacy_state_lock:
        current_frame = None
        current_boxes = []
    return get_source_status()


def set_default_source(source_key):
    """Select the legacy/default stream without stopping other workers."""
    global _default_source_key, current_mode, current_source_path, source_changed
    if not is_known_source(source_key):
        return False
    if not start_source_worker(source_key):
        return False
    with _manager_lock:
        _default_source_key = source_key
        source_config = runtime_settings.VIDEO_SOURCES[source_key]
        current_mode = source_config["mode"]
        current_source_path = source_config["uri"]
        source_changed = False
        oracle_service.CURRENT_ACTIVE_SOURCE = source_key
    worker = _workers[source_key]
    frame = worker.snapshot_frame()
    boxes = worker.snapshot_boxes()
    with _legacy_state_lock:
        global current_frame, current_boxes
        current_frame = frame
        current_boxes = boxes
    print(f"[YOLO] default stream selected: {source_key}")
    return True


def get_latest_frame(source_key=None):
    source_key = source_key or get_default_source_key()
    worker = _workers.get(source_key)
    if worker is None:
        return None
    return worker.snapshot_frame()


def get_latest_boxes(source_key=None):
    source_key = source_key or get_default_source_key()
    worker = _workers.get(source_key)
    if worker is None:
        return []
    return worker.snapshot_boxes()


def get_source_status():
    return {source_key: worker.status() for source_key, worker in _workers.items()}


def stream_client_opened():
    global active_connections
    with _legacy_state_lock:
        active_connections += 1


def stream_client_closed():
    global active_connections
    with _legacy_state_lock:
        active_connections = max(0, active_connections - 1)


def change_ai_source_runtime(mode, path_or_url):
    """Compatibility adapter for the former single-source switch API."""
    if mode == "esp32":
        return set_default_source("esp32")
    for source_key, source_config in runtime_settings.VIDEO_SOURCES.items():
        if source_config["mode"] == "video" and source_config["uri"] == path_or_url:
            return set_default_source(source_key)
    print(f"[YOLO] ignored unknown legacy source path: {path_or_url}")
    return False


def video_capture_and_detect():
    """Legacy entry point retained for callers using the old worker target."""
    start_all_workers()


# The former single worker is intentionally not started. The default is also
# deliberately OFF for every source; the Spring console's ON switch owns
# startup. An environment setting is available only for unattended operation.
ai_thread = None
if runtime_settings.AUTO_START_DETECTION_WORKERS:
    start_all_workers()
atexit.register(stop_all_workers)
