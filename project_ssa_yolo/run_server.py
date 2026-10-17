"""Single-process production-style entry point for the Flask YOLO server.

Use this instead of ``flask run --debug`` while OpenCV/FFmpeg, serial devices, or
background detection workers are active.  The reloader would create a second
process and can duplicate native resources.
"""

import os

from werkzeug.serving import make_server

from apps.environment import load_project_environment

# Configuration modules must see .env before create_app or its imports run.
load_project_environment()
from apps.app import create_app


def _port():
    try:
        return int(os.getenv("FLASK_RUN_PORT", "5000"))
    except ValueError:
        return 5000


app = create_app(os.getenv("SSA_FLASK_PROFILE", "ai").strip())


if __name__ == "__main__":
    server = make_server(
        host=os.getenv("FLASK_RUN_HOST", "0.0.0.0"),
        port=_port(),
        app=app,
        threaded=True,
    )
    # The token-protected endpoint starts this callback on a separate thread;
    # calling shutdown from a request handler itself would deadlock serve_forever.
    app.config["SSA_SERVER_SHUTDOWN"] = server.shutdown
    try:
        server.serve_forever()
    finally:
        server.server_close()
        from apps.services.yolo_detector import shutdown_ai_runtime
        shutdown_ai_runtime()
