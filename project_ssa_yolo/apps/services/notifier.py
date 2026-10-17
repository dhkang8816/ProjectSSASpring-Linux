"""Asynchronous Discord webhook notifications for completed YOLO events."""

import json
import mimetypes
import os
import threading
from queue import Empty, Full, Queue

import requests
from apps.environment import load_project_environment
from apps import runtime_settings


load_project_environment()

_notification_queue = Queue(maxsize=100)
_notification_start_lock = threading.Lock()
_notification_worker = None
_notification_shutdown_event = threading.Event()
_notification_status_lock = threading.Lock()
_notification_results = {"sentCount": 0, "failedCount": 0, "lastError": None}


def _safe_failure(error):
    """requests exceptions can contain the secret webhook URL; never stringify them."""
    response = getattr(error, "response", None)
    code = getattr(response, "status_code", None)
    detail = f"{type(error).__name__}" + (f" HTTP {code}" if code is not None else "")
    with _notification_status_lock:
        _notification_results["lastError"] = detail
    return detail



def _webhook_url():
    """Return the configured URL without ever including it in log output."""
    return os.getenv("DISCORD_WEBHOOK_URL", "").strip()


def _send_text_payload(webhook_url, payload):
    response = requests.post(webhook_url, json=payload, timeout=(3.0, 5.0))
    response.raise_for_status()


def send_discord_webhook(message, image_path=None):
    """Send one Discord message, optionally attaching an existing local snapshot.

    The function remains synchronous for backward compatibility. Production YOLO
    events must use :func:`enqueue_discord_alert`, which is consumed by the
    single notification worker below.
    """
    webhook_url = _webhook_url()
    if not webhook_url:
        print("[discord] DISCORD_WEBHOOK_URL is not configured; notification skipped")
        return False

    payload = {
        "content": str(message),
        "username": "Animal Protection AI",
    }

    if not image_path or not os.path.isfile(image_path):
        if image_path:
            print("[discord] snapshot is unavailable; sending text-only notification")
        try:
            _send_text_payload(webhook_url, payload)
            print("[discord] notification sent")
            return True
        except requests.RequestException as error:
            print(f"[discord] notification failed: {_safe_failure(error)}")
            return False

    try:
        mime_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
        with open(image_path, "rb") as image_file:
            files = {
                "files[0]": (
                    os.path.basename(image_path),
                    image_file,
                    mime_type,
                )
            }
            response = requests.post(
                webhook_url,
                data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                files=files,
                timeout=(3.0, 5.0),
            )
            response.raise_for_status()
        print("[discord] notification with snapshot sent")
        return True
    except (OSError, requests.RequestException) as error:
        # A file/read error must not discard the event's text notification.
        print(f"[discord] snapshot upload failed; sending text-only notification: {_safe_failure(error)}")
        try:
            _send_text_payload(webhook_url, payload)
            print("[discord] text-only fallback sent")
            return True
        except requests.RequestException as fallback_error:
            print(f"[discord] notification failed: {_safe_failure(fallback_error)}")
            return False


def send_discord_alert(message, image_path=None):
    """Clear semantic alias for callers that send a detection alert."""
    return send_discord_webhook(message, image_path=image_path)


def enqueue_discord_alert(message, image_path=None, event_type=None, drone_id=None, channel=None):
    """Queue a completed event without blocking a YOLO or Spring-report worker."""
    event = {
        "message": str(message),
        "image_path": image_path,
        "event_type": event_type,
        "drone_id": drone_id,
        "channel": channel,
    }
    try:
        _notification_queue.put_nowait(event)
        return True
    except Full:
        print("[discord] notification queue is full; event skipped")
        return False


def _notification_loop():
    while not _notification_shutdown_event.is_set():
        try:
            event = _notification_queue.get(timeout=0.5)
        except Empty:
            continue
        try:
            sent = send_discord_alert(event["message"], image_path=event.get("image_path"))
            with _notification_status_lock:
                _notification_results["sentCount" if sent else "failedCount"] += 1
                if sent:
                    _notification_results["lastError"] = None
                elif not _notification_results["lastError"]:
                    _notification_results["lastError"] = "Webhook not configured or delivery failed"
        except Exception as error:
            # Discord is optional: worker failures must never stop detection.
            print(f"[discord] notification worker error: {_safe_failure(error)}")
            with _notification_status_lock:
                _notification_results["failedCount"] += 1
        finally:
            _notification_queue.task_done()


def start_notification_service():
    """Start exactly one daemon worker, including under the Flask reloader."""
    global _notification_worker
    with _notification_start_lock:
        if _notification_worker is not None and _notification_worker.is_alive():
            return False
        _notification_shutdown_event.clear()
        _notification_worker = threading.Thread(
            target=_notification_loop,
            name="discord-notification-worker",
            daemon=True,
        )
        _notification_worker.start()
        print("[discord] notification worker started")
        return True


def stop_notification_service(join_timeout=2.0):
    """Stop the optional notification worker without blocking Flask exit."""
    global _notification_worker
    _notification_shutdown_event.set()
    thread = _notification_worker
    if thread is not None and thread is not threading.current_thread():
        thread.join(join_timeout)
    if thread is None or not thread.is_alive():
        _notification_worker = None
        print("[discord] notification worker stopped")
        return True
    print("[discord] notification worker did not stop before timeout")
    return False


def get_notification_status():
    """Return configuration and queue state without exposing a webhook URL."""
    worker = _notification_worker
    with _notification_status_lock:
        return {
            **_notification_results,
            "enabled": runtime_settings.OPTIONAL_IO_ENABLED,
            "configured": bool(_webhook_url()),
            "workerRunning": worker is not None and worker.is_alive(),
            "queueDepth": _notification_queue.qsize(),
        }
