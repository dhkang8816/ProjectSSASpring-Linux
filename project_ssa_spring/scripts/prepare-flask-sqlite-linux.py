"""Review/copy an existing Flask SQLite DB into a private Linux runtime store.

Default is read-only. --apply requires root and explicit operator approval.
Does not modify the source DB, model, credentials, firewall or Windows settings.
"""

import argparse
from contextlib import closing
import grp
import hashlib
import os
from pathlib import Path
import pwd
import re
import socket
import sqlite3
import subprocess
import tempfile


def fingerprint(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").digest()


def database_fingerprint(path):
    """Compare schema/data without logging rows or relying on SQLite file headers."""
    digest = hashlib.sha256()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as database:
        if database.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SystemExit("Retained SQLite copy failed integrity validation")
        for statement in database.iterdump():
            digest.update(statement.encode())
            digest.update(b"\n")
    return digest.digest()


def validate_retained_copy(source, destination):
    if not destination.is_file() or database_fingerprint(source) != database_fingerprint(destination):
        raise SystemExit("Retained DB differs from source; refusing to reuse or overwrite it")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resume", action="store_true", help="reuse only a verified identical retained DB")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    source = repository / "project_ssa_yolo/local.sqlite"
    environment = repository / "project_ssa_yolo/.env"
    destination = args.destination
    if not destination.is_absolute() or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(destination)):
        raise SystemExit("Destination must be an absolute Linux path without shell/systemd metacharacters")
    # Limit this administrator helper to application data, never source/system dirs.
    runtime_root = Path("/var/lib/project-ssa")
    if not destination.is_relative_to(runtime_root) or destination.parent.parent != runtime_root:
        raise SystemExit("Use a dedicated subdirectory under /var/lib/project-ssa")
    for ancestor in (destination, *destination.parents):
        if ancestor.is_symlink() or ".." in ancestor.parts:
            raise SystemExit("Destination must not contain symlinks or parent traversal")
    if args.resume:
        validate_retained_copy(source, destination)
        if set(destination.parent.iterdir()) != {destination}:
            raise SystemExit("Retained directory has other files; manual review is required")
    else:
        if destination.exists():
            raise SystemExit("Destination already exists; refusing to overwrite data")
        if destination.parent.exists():
            raise SystemExit("Choose a new dedicated directory; existing directories are not altered")
    if not source.is_file():
        raise SystemExit("Approved source SQLite is unavailable")
    with source.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\0":
            raise SystemExit("Source is not an initialized SQLite DB")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as database:
        if database.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SystemExit("Source SQLite integrity check failed")
    raw = environment.read_bytes()
    matches = list(re.finditer(rb"(?m)^SSA_SQLITE_PATH=[^\r\n]*", raw))
    if len(matches) != 1:
        raise SystemExit("Expected exactly one approved SSA_SQLITE_PATH setting")
    setting = matches[0]
    if setting.group().split(b"=", 1)[1].decode() != str(source):
        raise SystemExit("SSA_SQLITE_PATH changed; review before proceeding")
    replacement = b"SSA_SQLITE_PATH=" + str(destination).encode()
    updated = raw[:setting.start()] + replacement + raw[setting.end():]
    dropin = Path("/etc/systemd/system/tomcat10.service.d/ssa-flask-sqlite.conf")
    if dropin.exists():
        raise SystemExit("SQLite service drop-in already exists; refusing to overwrite it")
    service_user = pwd.getpwnam("tomcat")
    shared_group = grp.getgrnam("ssa-upload")
    print("Read-only preflight: existing SQLite integrity and one-key environment update OK")
    print("Proposed: copy approved SQLite to", destination)
    print("Proposed: runtime directory tomcat:ssa-upload 2770, DB tomcat:ssa-upload 0660")
    print("Proposed: one ReadWritePaths exception, SSA_SQLITE_PATH update, Tomcat restart")
    if not args.apply:
        print("No DB, environment, permission or service changes were made")
        return
    if os.geteuid() != 0:
        raise SystemExit("Administrator authentication is required for --apply")
    # Do not migrate around a separately running Flask process.
    try:
        with socket.create_connection(("127.0.0.1", 5000), timeout=1):
            raise SystemExit("Flask is listening on port 5000; stop it normally before applying")
    except ConnectionRefusedError:
        pass
    source_hash = fingerprint(source)
    backup = Path(tempfile.mkdtemp(prefix="project-ssa-sqlite.", dir="/var/backups"))
    backup.chmod(0o700)
    # Record only the non-secret setting needed for rollback, not the .env contents.
    (backup / "previous-sqlite-setting.txt").write_bytes(setting.group() + b"\n")
    runtime_root.mkdir(mode=0o755, exist_ok=True)
    if not args.resume:
        destination.parent.mkdir(mode=0o700)
    os.chown(destination.parent, service_user.pw_uid, shared_group.gr_gid)
    destination.parent.chmod(0o2770)
    if not args.resume:
        # Reserve without overwriting, then SQLite's backup API makes a consistent copy.
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(destination)) as copied:
                original.backup(copied)
    validate_retained_copy(source, destination)
    os.chown(destination, service_user.pw_uid, shared_group.gr_gid)
    destination.chmod(0o660)
    if fingerprint(source) != source_hash:
        raise SystemExit("Source changed during copy; review retained destination before using it")
    for path in (runtime_root, destination.parent, destination):
        command = ["runuser", "-u", "tomcat", "--", "test"]
        subprocess.run(command + ["-r", str(path)], check=True)
        if path != runtime_root:
            subprocess.run(command + ["-w", str(path)], check=True)
        if path.is_dir():
            subprocess.run(command + ["-x", str(path)], check=True)
    dropin.parent.mkdir(mode=0o755, exist_ok=True)
    with dropin.open("x") as output:
        output.write("[Service]\nReadWritePaths=" + str(destination.parent) + "\n")
    dropin.chmod(0o644)
    # Keep file ownership, mode and ACLs; replace only the approved non-secret key.
    if environment.read_bytes() != raw:
        raise SystemExit("Environment changed concurrently; retained copy/drop-in need review")
    with environment.open("r+b") as output:
        output.write(updated)
        output.truncate()
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "tomcat10"], check=True)
    subprocess.run(["systemctl", "is-active", "--quiet", "tomcat10"], check=True)
    print("Original DB preserved; runtime copy and Tomcat restart completed")
    print("Rollback setting record:", backup)
    print("Start Flask normally, then verify health and AI; no test notification was sent")


if __name__ == "__main__":
    main()
