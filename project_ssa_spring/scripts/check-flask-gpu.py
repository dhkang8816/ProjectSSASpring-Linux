"""Run only the isolated Spring/Flask GPU lifecycle test, without deployment."""

import argparse
import hashlib
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="fingerprint of an owner-trusted checkpoint")
    args = parser.parse_args()
    model = args.model.resolve(strict=True)
    with model.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != args.sha256:
            raise RuntimeError("Checkpoint identity differs; test refused")
    spring = Path(__file__).resolve().parents[1]
    project = spring.parent / "project_ssa_yolo"
    if not (project / ".venv/bin/python").is_file():
        raise RuntimeError("Prepare the project Linux .venv first")
    with tempfile.TemporaryDirectory(prefix="ssa-flask-gpu-test-") as temporary:
        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = port_socket.getsockname()[1]
        environment = dict(os.environ)
        environment.update(SSA_RUN_GPU_INTEGRATION="true", SSA_GPU_TEST_PROJECT_DIR=str(project),
                           SSA_YOLO_MODEL_PATH=str(model), SSA_YOLO_DEVICE="cuda:0",
                           SSA_SQLITE_PATH="", SSA_FLASK_PROFILE="ai", SSA_AUTO_START_DETECTION_WORKERS="false",
                           SSA_OPTIONAL_IO_ENABLED="false", SSA_FLASK_CONTROL_TOKEN=secrets.token_urlsafe(32),
                           SSA_BUZZER_STARTUP_SOUND_ENABLED="false", SSA_BUZZER_SHUTDOWN_SOUND_ENABLED="false",
                           FLASK_RUN_HOST="127.0.0.1", FLASK_RUN_PORT=str(port), YOLO_CONFIG_DIR=temporary,
                           YOLO_AUTOINSTALL="false", YOLO_OFFLINE="true", PYTHONDONTWRITEBYTECODE="1")
        # Ultralytics expects its config parent to exist. This is test data only.
        # The child Flask inherits stdout; a Surefire fork would interpret its
        # native output as protocol data. Keep this focused lifecycle test in-process.
        return subprocess.run(["mvn", "-o", "-DforkCount=0", "-Dtest=FlaskRuntimeReadinessTest", "test"],
                              cwd=spring, env=environment).returncode


if __name__ == "__main__":
    raise SystemExit(main())
