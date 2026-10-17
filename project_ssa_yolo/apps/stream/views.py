import hmac
import os
import threading
import time

import cv2
import numpy as np
from flask import Blueprint, Response, current_app, jsonify, render_template, request, stream_with_context

from apps.app import csrf
from apps.services import buzzer_helper, notifier, sensor_helper, yolo_detector


stream = Blueprint(
    "stream",
    __name__,
    template_folder="templates",
    static_folder="static",
)


@stream.route("/")
def index():
    if not current_app.config.get("LOCAL_DATABASE_ENABLED", True):
        return jsonify({"profile": "ai", "health": "/stream/health"})
    return render_template("index.html")


@stream.route("/video_feed")
def video_feed():
    """Backward-compatible stream for the selected/default source."""
    return _video_response(yolo_detector.get_default_source_key())


@stream.route("/video_feed/<source_key>")
def video_feed_by_source(source_key):
    if not yolo_detector.is_known_source(source_key):
        return jsonify({"error": "unknown source_key", "source_key": source_key}), 404
    return _video_response(source_key)


def _video_response(source_key):
    # The lifecycle API is the single authority for ON/OFF.  Starting a worker
    # merely because an old MJPEG connection still exists would immediately
    # undo a user's "탐지 중지" action.
    return Response(
        stream_with_context(generate_frames(source_key)),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


def generate_frames(source_key=None):
    """Encode only the requested source's latest completed YOLO frame."""
    source_key = source_key or yolo_detector.get_default_source_key()
    yolo_detector.stream_client_opened()
    print(f"[Stream {source_key}] client connected")
    try:
        while True:
            worker_status = yolo_detector.get_source_status().get(source_key, {})
            # Finish stale Spring proxy connections as soon as their channel is
            # stopped. The JSP removes src first, but this also covers delayed
            # browser/Tomcat disconnects.
            if worker_status.get("stopped"):
                break
            frame = yolo_detector.get_latest_frame(source_key)
            if frame is None:
                frame = _waiting_frame(source_key)
            encoded, buffer = cv2.imencode(".jpg", frame)
            if encoded:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + buffer.tobytes()
                    + b"\r\n"
                )
            time.sleep(0.03)
    except (GeneratorExit, BrokenPipeError, ConnectionResetError):
        # A browser/Spring proxy disconnect only ends this HTTP generator.
        pass
    finally:
        yolo_detector.stream_client_closed()
        print(f"[Stream {source_key}] client disconnected")


def _waiting_frame(source_key):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(
        frame,
        f"CONNECTING: {source_key}",
        (120, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
    )
    return frame


@stream.route("/labels_feed")
def labels_feed():
    """Backward-compatible labels for the selected/default source."""
    return jsonify({"boxes": yolo_detector.get_latest_boxes()})


@stream.route("/labels_feed/<source_key>")
def labels_feed_by_source(source_key):
    if not yolo_detector.is_known_source(source_key):
        return jsonify({"error": "unknown source_key", "source_key": source_key}), 404
    return jsonify({"boxes": yolo_detector.get_latest_boxes(source_key)})


@stream.route("/status")
def source_status():
    """Expose per-source worker state for operational diagnostics."""
    return jsonify(_status_payload())


def _status_payload():
    return {
        "default_source": yolo_detector.get_default_source_key(),
        "sources": yolo_detector.get_source_status(),
    }


@stream.route("/health")
def health_status():
    """Read-only process health used by the Spring administrator diagnostics.

    This endpoint deliberately reads existing in-memory state only. It never
    starts a YOLO worker, runs inference, invokes mpremote, or sends Discord.
    """
    response = jsonify({
        **_status_payload(),
        **current_app.extensions["ssa_runtime_status"](),
        "instanceId": str(os.getpid()),
        "reports": yolo_detector.oracle_service.get_report_status(),
        "sensor": sensor_helper.get_sensor_service_status(),
        "buzzer": buzzer_helper.get_buzzer_status(),
        "discord": notifier.get_notification_status(),
    })
    response.headers["Cache-Control"] = "no-store"
    return response


@stream.route("/admin/shutdown", methods=["POST"])
@csrf.exempt
def shutdown_runtime():
    """Request a graceful local run_server.py shutdown from Spring admin UI.

    The endpoint is intentionally unavailable unless a non-empty control token
    is configured.  ``run_server.py`` supplies the callback only for its
    single-process server mode; other WSGI deployments receive a safe 503.
    """
    configured_token = os.getenv("SSA_FLASK_CONTROL_TOKEN", "")
    request_token = request.headers.get("X-SSA-Flask-Control-Token", "")
    if not configured_token or not hmac.compare_digest(configured_token, request_token):
        return jsonify({"status": "FAIL", "error": "unauthorized"}), 403

    shutdown_callback = current_app.config.get("SSA_SERVER_SHUTDOWN")
    if not callable(shutdown_callback):
        return jsonify({"status": "FAIL", "error": "managed runtime shutdown unavailable"}), 503

    threading.Thread(
        target=shutdown_callback,
        name="flask-runtime-shutdown",
        daemon=True,
    ).start()
    return jsonify({"status": "SUCCESS", "message": "shutdown requested"})


@stream.route("/buzzer/enabled", methods=["GET", "POST"])
@csrf.exempt
def control_buzzer_enabled():
    """Read or update the sound-only state shared by the buzzer worker."""
    if request.method == "POST":
        payload = request.get_json(silent=True) or request.form.to_dict()
        if "enabled" not in payload:
            return jsonify({"status": "FAIL", "error": "enabled is required"}), 400

        enabled = payload["enabled"]
        if isinstance(enabled, str):
            normalized = enabled.strip().lower()
            if normalized not in {"true", "false", "1", "0", "on", "off"}:
                return jsonify({"status": "FAIL", "error": "enabled must be boolean"}), 400
            enabled = normalized in {"true", "1", "on"}
        elif not isinstance(enabled, bool):
            return jsonify({"status": "FAIL", "error": "enabled must be boolean"}), 400

        buzzer_helper.set_buzzer_enabled(enabled)

    return jsonify({"status": "SUCCESS", "enabled": buzzer_helper.is_buzzer_enabled()})


@stream.route("/sensor/status")
def sensor_status():
    """Return cached board sensors without starting a USB command per request."""
    return jsonify(sensor_helper.get_latest_sensor_status())


@stream.route("/battery/status")
def battery_status():
    """Return cached ESP32 battery telemetry without opening COM on demand."""
    return jsonify(sensor_helper.get_latest_battery_status())


@stream.route("/battery/status/<source_key>")
def battery_status_by_source(source_key):
    """Only the configured physical board source exposes the battery value."""
    if not yolo_detector.is_known_source(source_key):
        return jsonify({"error": "unknown source_key", "source_key": source_key}), 404
    return jsonify(sensor_helper.get_latest_battery_status(source_key))


@stream.route("/detection/<source_key>/<action>", methods=["POST"])
@csrf.exempt
def control_source_detection(source_key, action):
    """Start or stop one worker for the Spring-side channel power switch."""
    if not yolo_detector.is_known_source(source_key):
        return jsonify({"status": "FAIL", "error": "unknown source_key", "source_key": source_key}), 404
    if action == "start":
        completed = yolo_detector.start_source_worker(source_key)
    elif action == "stop":
        completed = yolo_detector.stop_source_worker(source_key)
    else:
        return jsonify({"status": "FAIL", "error": "unknown action", "action": action}), 400

    payload = _status_payload()
    payload.update({"status": "SUCCESS" if completed else "FAIL", "source_key": source_key, "action": action})
    return jsonify(payload), 200 if completed else 503


@stream.route("/detection/<action>", methods=["POST"])
@csrf.exempt
def control_all_detection(action):
    """All-channel lifecycle API retained for operational control clients."""
    if action == "start":
        source_statuses = yolo_detector.start_all_workers()
        completed = all(status["running"] for status in source_statuses.values())
    elif action == "stop":
        source_statuses = yolo_detector.stop_all_workers()
        completed = all(status["stopped"] for status in source_statuses.values())
    else:
        return jsonify({"status": "FAIL", "error": "unknown action", "action": action}), 400

    payload = _status_payload()
    payload.update({"status": "SUCCESS" if completed else "FAIL", "action": action})
    return jsonify(payload), 200 if completed else 503


@stream.route("/change_source/<source_key>")
def change_hybrid_source(source_key):
    """Keep the old switch API but only change the default stream.

    All configured source workers keep running, so selecting one source no
    longer shuts down or replaces another source's detection pipeline.
    """
    if not yolo_detector.is_known_source(source_key):
        return jsonify({"status": "FAIL", "error": "unknown source_key", "source_key": source_key}), 404
    if not yolo_detector.set_default_source(source_key):
        return jsonify({"status": "FAIL", "mode": source_key, **_status_payload()}), 503
    return jsonify({"status": "SUCCESS", "mode": source_key})
