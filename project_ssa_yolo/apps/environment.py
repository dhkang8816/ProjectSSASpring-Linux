"""Load this application's local environment independently of the working directory."""

from pathlib import Path
import os

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPOSITORY_ROOT / "project_ssa_yolo"


def load_project_environment():
    """Keep service/shell variables authoritative over the project's local .env."""
    loaded = load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)
    # Local custom weights are supplied by the operator, never auto-installed.
    os.environ.setdefault("YOLO_OFFLINE", "true")
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    return loaded
