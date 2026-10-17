"""Serialize ESP32 buzzer commands without blocking YOLO workers.

The ESP32 board is controlled through the configured ``mpremote`` serial port
(Windows retains its ``COM6`` default; Linux requires an explicit device).
Only this module invokes mpremote, and one daemon worker owns the queue so two
threads never open the COM port concurrently.
"""

import queue
import subprocess
import sys
import threading

from apps import runtime_settings


_buzzer_queue = queue.Queue()
_worker_lock = threading.Lock()
_worker_thread = None
_shutdown_event = threading.Event()
_state_lock = threading.Lock()
_buzzer_enabled = True
_collision_level = "SAFE"
_mpremote_lock = threading.Lock()

_MPREMOTE_PREFIX = (sys.executable, "-m", "mpremote")
_COMMANDS = {
    "animal": ("resume", "exec", "import main; main.play_animal_alert()"),
    "danger": ("resume", "exec", "import main; main.play_danger_alert()"),
    # Do not use ``resume`` for the one-time startup command.  mpremote then
    # performs its normal soft-reset/REPL synchronisation, which reloads
    # ``main.py`` and creates a fresh PWM object before the long-lived
    # ``resume`` commands are used for detection alerts.  This is the same
    # recovery path as a manual ``mpremote connect COMx exec ...`` command.
    "startup": ("exec", "import main; main.play_startup_melody()"),
    "shutdown": ("resume", "exec", "import main; main.play_shutdown_melody()"),
}
_ERROR_MESSAGES = {
    "animal": "animal buzzer command failed",
    "danger": "danger buzzer command failed",
    "startup": "startup buzzer command failed",
    "shutdown": "shutdown buzzer command failed",
}


def run_mpremote(arguments, timeout=15, capture_output=False):
    """Run this interpreter's mpremote module without relying on PATH."""
    arguments = list(arguments)
    if "connect" in arguments:
        index = arguments.index("connect") + 1
        if index >= len(arguments):
            raise runtime_settings.RuntimePathError("SSA_ESP32_COM_PORT must be configured")
        arguments[index] = runtime_settings.validate_serial_port(arguments[index])
    command = [*_MPREMOTE_PREFIX, *arguments]
    with _mpremote_lock:
        return subprocess.run(
            command,
            shell=False,
            check=True,
            timeout=timeout,
            capture_output=capture_output,
            text=capture_output,
        )


def _run_mpremote_command(alert_type):
    """Run one existing mpremote command; failures must not stop the worker."""
    try:
        if alert_type.startswith("collision:"):
            level = alert_type.split(":", 1)[1]
            command = (
                "connect", runtime_settings.ESP32_COM_PORT, "resume", "exec",
                f"import main; main.play_collision_alert('{level}')",
            )
        else:
            command = ("connect", runtime_settings.ESP32_COM_PORT, *_COMMANDS[alert_type])
        run_mpremote(command, capture_output=True)
    except Exception as error:
        message = _ERROR_MESSAGES.get(alert_type, "collision buzzer command failed")
        stderr = getattr(error, "stderr", None)
        stdout = getattr(error, "stdout", None)
        detail = stderr or stdout or str(error)
        print(f"[buzzer] {message}: {str(detail).strip()}")


def _buzzer_worker():
    """Consume commands one at a time to protect the shared USB COM port."""
    while not _shutdown_event.is_set():
        try:
            alert_type, completed = _buzzer_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            # Recheck immediately before USB access so an OFF change also
            # suppresses alerts that were already waiting in the queue.
            if is_buzzer_enabled():
                _run_mpremote_command(alert_type)
        finally:
            if completed is not None:
                completed.set()
            _buzzer_queue.task_done()


def start_buzzer_service():
    """Start exactly one daemon worker for this Python process."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return False
        _shutdown_event.clear()
        _worker_thread = threading.Thread(
            target=_buzzer_worker,
            name="esp32-buzzer-worker",
            daemon=True,
        )
        _worker_thread.start()
        print("[buzzer] service worker started")
        return True


def stop_buzzer_service(join_timeout=2.0):
    """Request clean shutdown without waiting indefinitely for USB I/O."""
    global _worker_thread
    _shutdown_event.set()
    thread = _worker_thread
    if thread is not None and thread is not threading.current_thread():
        thread.join(join_timeout)
    if thread is None or not thread.is_alive():
        _worker_thread = None
        print("[buzzer] service worker stopped")
        return True
    print("[buzzer] service worker did not stop before timeout")
    return False


def is_buzzer_service_running():
    """Return whether this process already owns an active buzzer worker."""
    worker = _worker_thread
    return worker is not None and worker.is_alive()


def _enqueue(alert_type, completed=None):
    if not is_buzzer_enabled():
        return False
    start_buzzer_service()
    _buzzer_queue.put((alert_type, completed))
    return True


def _discard_pending_events():
    """Drop alerts waiting in the queue after an operator switches OFF."""
    while True:
        try:
            _buzzer_queue.get_nowait()
        except queue.Empty:
            return
        else:
            _buzzer_queue.task_done()


def set_buzzer_enabled(enabled):
    """Set the process-wide sound state; OFF never changes YOLO processing."""
    global _buzzer_enabled
    enabled = bool(enabled)
    with _state_lock:
        _buzzer_enabled = enabled
    if not enabled:
        _discard_pending_events()
    print(f"[buzzer] sound {'enabled' if enabled else 'disabled'}")
    return enabled


def is_buzzer_enabled():
    """Return the process-wide sound state used by enqueue and worker paths."""
    with _state_lock:
        return _buzzer_enabled


def get_buzzer_status():
    """Return worker state only; this function never opens the ESP32 port."""
    with _state_lock:
        enabled = _buzzer_enabled
        collision_level = _collision_level

    worker = _worker_thread
    return {
        "enabled": enabled,
        "collisionLevel": collision_level,
        "workerRunning": worker is not None and worker.is_alive(),
        "queueDepth": _buzzer_queue.qsize(),
    }


def set_collision_level(level):
    """Queue one tone for a level transition; polling never floods COM."""
    global _collision_level
    level = str(level or "UNKNOWN").upper()
    if level not in {"SAFE", "CAUTION", "WARNING", "DANGER", "UNKNOWN"}:
        level = "UNKNOWN"

    with _state_lock:
        changed = level != _collision_level
        _collision_level = level

    if changed and level in {"CAUTION", "WARNING", "DANGER"}:
        _enqueue(f"collision:{level}")
    return level


def trigger_animal_sound():
    """Queue an animal-under-target alert and return immediately."""
    _enqueue("animal")


def trigger_danger_sound():
    """Queue a danger-object alert and return immediately."""
    _enqueue("danger")


def play_startup_melody():
    """Queue one short startup sound through the existing COM owner."""
    return _enqueue("startup")


def play_shutdown_melody(wait_timeout):
    """Queue the one-time shutdown tone and wait only for that command.

    The completion event is set after the serial attempt, including a bounded
    mpremote failure.  Flask shutdown therefore never waits indefinitely.
    """
    completed = threading.Event()
    if not _enqueue("shutdown", completed):
        return False
    return completed.wait(wait_timeout)
