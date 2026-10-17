"""Load this application's local environment independently of the working directory."""

from pathlib import Path

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPOSITORY_ROOT / "project_ssa_yolo"


def load_project_environment():
    """Keep service/shell variables authoritative over the project's local .env."""
    return load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)
