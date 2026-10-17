"""Application service bootstrap helpers."""

import threading

from apps import runtime_settings
from apps.services.buzzer_helper import (
    play_startup_melody,
    play_shutdown_melody,
    is_buzzer_service_running,
    start_buzzer_service,
    stop_buzzer_service,
)
from apps.services.notifier import start_notification_service, stop_notification_service
from apps.services.sensor_helper import start_sensor_service, stop_sensor_service


_startup_sound_lock = threading.Lock()
_startup_sound_played = False
_startup_status_lock = threading.RLock()
_startup_status = {
    "stage": "IDLE",
    "progress": 0,
    "label": "서비스 시작 대기",
    "ready": False,
}


def _set_startup_status(stage, progress, label, ready=False):
    with _startup_status_lock:
        _startup_status.update({
            "stage": stage,
            "progress": int(progress),
            "label": label,
            "ready": bool(ready),
        })


def mark_startup_requested():
    """Record the control-plane request before optional workers are started."""
    _set_startup_status("SERVICES_STARTING", 70, "부가 서비스 시작 요청", False)


def mark_startup_failed():
    _set_startup_status("SERVICE_FAILED", 0, "부가 서비스 시작 실패", False)


def get_startup_status():
    """Return a stable snapshot for the token-protected runtime status route."""
    with _startup_status_lock:
        return dict(_startup_status)


def start_services():
    """Initialize optional workers and queue at most one process startup tone."""

    global _startup_sound_played
    if not runtime_settings.OPTIONAL_IO_ENABLED:
        _set_startup_status("READY", 100, "장치·알림 worker 비활성화", True)
        return
    _set_startup_status("SERVICES_STARTING", 70, "부가 서비스 시작 중", False)
    print("[starter] services starting")
    start_buzzer_service()
    _set_startup_status("BUZZER_READY", 78, "부저 워커 시작", False)
    start_sensor_service()
    _set_startup_status("SENSOR_READY", 86, "센서 워커 시작", False)
    start_notification_service()
    _set_startup_status("DISCORD_READY", 94, "Discord 알림 워커 시작", False)

    if runtime_settings.BUZZER_STARTUP_SOUND_ENABLED:
        with _startup_sound_lock:
            if not _startup_sound_played:
                # This only enqueues.  ESP32/mpremote failures stay in the existing
                # worker and must never make Flask startup fail.
                play_startup_melody()
                _startup_sound_played = True
    _set_startup_status("READY", 100, "부가 서비스 준비 완료", True)
    print("[starter] services ready")


def stop_services():
    """Stop optional background services during Flask process shutdown."""
    stop_notification_service()
    stop_sensor_service()
    # The sensor poller and buzzer share one mpremote lock.  Stop polling
    # first, then give the queued shutdown tone a bounded chance to own COM6.
    # A muted console intentionally stays silent during shutdown as well.
    if (
        runtime_settings.BUZZER_SHUTDOWN_SOUND_ENABLED
        and is_buzzer_service_running()
    ):
        play_shutdown_melody(runtime_settings.BUZZER_SHUTDOWN_SOUND_WAIT_SECONDS)
    stop_buzzer_service()
