"""Read-only path checks; never import the app, create files, or contact services."""

import argparse
import os
from pathlib import Path, PureWindowsPath
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _access(path, mode):
    if os.access in os.supports_effective_ids:
        return os.access(path, mode, effective_ids=True)
    return os.access(path, mode)


def inspect_path(name, value, *, directory=False, writable=False):
    """Report access for this process identity without disclosing configured values."""
    if not value or not value.strip():
        return name, "NOT_CONFIGURED"
    try:
        if "://" in value or (os.name != "nt" and PureWindowsPath(value).drive):
            return name, "INVALID_OS_PATH"
        path = Path(value).expanduser()
        if directory and not path.is_absolute():
            return name, "ABSOLUTE_PATH_REQUIRED"
        if not path.is_absolute():
            path = REPOSITORY_ROOT / path
        if not path.exists():
            parent = path.parent
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            allowed = _access(parent, os.W_OK | os.X_OK)
            return name, f"MISSING (existing ancestor write/search={allowed})"
        if directory != path.is_dir() or (not directory and not path.is_file()):
            return name, "WRONG_FILE_TYPE"
        if not _access(path, os.R_OK | (os.X_OK if directory else 0)):
            return name, "NO_READ_OR_DIRECTORY_SEARCH_ACCESS"
        if writable and not _access(path, os.W_OK | (os.X_OK if directory else 0)):
            return name, "NO_WRITE_ACCESS"
        if writable and not directory and not _access(path.parent, os.W_OK | os.X_OK):
            return name, "NO_PARENT_WRITE_OR_SEARCH_ACCESS"
        return name, "OK"
    except (OSError, ValueError, RuntimeError):
        return name, "INACCESSIBLE_OR_INVALID_PATH"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spring", action="store_true",
                        help="check shell environment only; do not read Flask .env or JVM properties")
    args = parser.parse_args()
    if not args.spring:
        sys.path.insert(0, str(REPOSITORY_ROOT / "project_ssa_yolo"))
        from apps.environment import load_project_environment
        load_project_environment()

    upload_default = "C:/upload" if os.name == "nt" else "/var/lib/project-ssa/uploads"
    checks = [inspect_path("SSA_UPLOAD_ROOT", os.getenv("SSA_UPLOAD_ROOT", "").strip() or upload_default,
                           directory=True, writable=True)]
    if args.spring:
        cache_default = (os.getenv("SSA_UPLOAD_ROOT", "").strip() or upload_default) if os.name == "nt" else "/var/cache/project-ssa"
        checks.append(inspect_path("SSA_CACHE_ROOT", os.getenv("SSA_CACHE_ROOT", "").strip() or cache_default,
                                   directory=True, writable=True))
        print("Scope: this shell's Spring environment; JVM properties and service environment are not inspected")
    else:
        for name in ["SSA_YOLO_MODEL_PATH", "SSA_VIDEO_1_PATH", "SSA_VIDEO_2_PATH", "SSA_VIDEO_3_PATH", "SSA_SQLITE_PATH"]:
            checks.append(inspect_path(name, os.getenv(name, ""), writable=name == "SSA_SQLITE_PATH"))
        print("Scope: Flask process environment > project .env")
    identity = f"uid={os.geteuid()}" if hasattr(os, "geteuid") else "current Windows process identity"
    print(f"Permission checks: {identity}; read-only access checks, no write probes")
    for name, status in checks:
        print(f"{name}: {status}")
    return 0 if all(status == "OK" for _, status in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
