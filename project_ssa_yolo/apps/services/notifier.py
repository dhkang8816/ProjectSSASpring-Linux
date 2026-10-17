"""Asynchronous Discord webhook notifications for completed YOLO events."""

import json
import mimetypes
import os
import threading
from queue import Empty, Full, Queue

import requests
from apps.environment import load_project_environment


load_project_environment()

_notification_queue = Queue(maxsize=100)
_notification_start_lock = threading.Lock()
_notification_worker = None
_notification_shutdown_event = threading.Event()


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
            print(f"[discord] notification failed: {error}")
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
        print(f"[discord] snapshot upload failed; sending text-only notification: {error}")
        try:
            _send_text_payload(webhook_url, payload)
            print("[discord] text-only fallback sent")
            return True
        except requests.RequestException as fallback_error:
            print(f"[discord] notification failed: {fallback_error}")
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
            send_discord_alert(event["message"], image_path=event.get("image_path"))
        except Exception as error:
            # Discord is optional: worker failures must never stop detection.
            print(f"[discord] notification worker error: {error}")
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
    return {
        "configured": bool(_webhook_url()),
        "workerRunning": worker is not None and worker.is_alive(),
        "queueDepth": _notification_queue.qsize(),
    }
