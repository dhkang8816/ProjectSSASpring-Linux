"""Compatibility routes for the ESP32 view.

ESP32 capture and YOLO inference now belong to the shared multi-source detector
manager. Keeping these routes avoids breaking the existing Flask templates and
Spring proxy while preventing a second ESP32 model/receiver from being created.
"""

import time

import cv2
import numpy as np
from flask import Blueprint, Response, current_app, jsonify, render_template, stream_with_context

from apps.services import oracle_service, yolo_detector


esp32_yolov12 = Blueprint(
    "esp32_yolov12",
    __name__,
    template_folder="templates",
    static_folder="static",
)

# These names are retained for compatibility with legacy templates/callers.
esp32_current_frame = None
esp32_boxes = []
esp_mode_active = False
has_resetted = False


@esp32_yolov12.route("/")
def index():
    if not current_app.config.get("LOCAL_DATABASE_ENABLED", True):
        return jsonify({"profile": "ai", "health": "/stream/health"})
    oracle_service.fetch_target_counts()
    total_animal_count = sum(yolo_detector.TARGET_ANIMALS.values())
    return render_template(
        "esp32/index.html",
        animal_count=total_animal_count,
        danger_detect=0,
        animal_detect=0,
    )


def start_esp32_receiver():
    """Legacy lifecycle hook delegated to the source-worker manager."""
    global esp_mode_active
    esp_mode_active = yolo_detector.start_source_worker("esp32")
    return esp_mode_active


def stop_esp32_receiver():
    """Explicit legacy stop hook; it releases the ESP32 VideoCapture."""
    global esp_mode_active, esp32_current_frame, esp32_boxes
    esp_mode_active = False
    esp32_current_frame = None
    esp32_boxes = []
    return yolo_detector.stop_source_worker("esp32")


def esp32_video_stream_receiver(generation=None):
    """Former worker target retained as a no-duplicate-worker adapter."""
    return start_esp32_receiver()


@esp32_yolov12.route("/change_mode/<mode_name>")
def change_mode_signal(mode_name):
    global has_resetted
    has_resetted = False
    if mode_name == "esp32":
        completed = yolo_detector.set_default_source("esp32") and start_esp32_receiver()
    else:
        # Preserve the old video-mode intent without stopping the other source
        # workers that now provide concurrent monitoring.
        completed = yolo_detector.set_default_source("video_1")
    if not completed:
        return jsonify({"status": "FAIL", "mode": mode_name, "sources": yolo_detector.get_source_status()}), 503
    return jsonify({"status": "mode_changed", "mode": mode_name})


def generate_esp32_frames_bridge():
    """Serve the ESP32 worker's annotated latest frame to legacy consumers."""
    global esp32_current_frame, esp32_boxes
    # Streaming is a read-only consumer.  The /stream/detection lifecycle API
    # is the sole authority that starts or stops the ESP32 source worker.
    print("[Stream esp32] legacy client connected")
    try:
        while True:
            frame = yolo_detector.get_latest_frame("esp32")
            esp32_boxes = yolo_detector.get_latest_boxes("esp32")
            if frame is None:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    frame,
                    "CONNECTING TO ESP32 CAM...",
                    (120, 240),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                )
            else:
                esp32_current_frame = frame
            encoded, buffer = cv2.imencode(".jpg", frame)
            if encoded:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + buffer.tobytes()
                    + b"\r\n"
                )
            time.sleep(0.04)
    except (GeneratorExit, BrokenPipeError, ConnectionResetError):
        pass
    finally:
        # This is a legacy HTTP consumer only; it does not own the capture.
        print("[Stream esp32] legacy client disconnected")


@esp32_yolov12.route("/video_feed")
def video_feed():
    return Response(
        stream_with_context(generate_esp32_frames_bridge()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@esp32_yolov12.route("/labels_feed")
def labels_feed():
    return jsonify({"boxes": yolo_detector.get_latest_boxes("esp32")})
