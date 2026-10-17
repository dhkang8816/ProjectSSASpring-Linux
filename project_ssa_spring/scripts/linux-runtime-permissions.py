"""Read-only Linux service audit; --verify adds disposable filesystem probes.

Run with the project venv Python under sudo for /proc and mount-namespace access.
Never prints environment values other than explicitly classified filesystem paths.
"""

import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
import uuid

REPOSITORY = Path(__file__).resolve().parents[2]
YOLO = REPOSITORY / "project_ssa_yolo"
SERVICE_KEYS = ["MainPID", "User", "Group", "SupplementaryGroups", "ProtectHome",
                "ProtectSystem", "ReadWritePaths", "ReadOnlyPaths", "InaccessiblePaths",
                "PrivateTmp", "NoNewPrivileges", "WorkingDirectory", "EnvironmentFiles", "UMask"]
PATH_KEYS = ["SSA_UPLOAD_ROOT", "SSA_CACHE_ROOT", "SSA_YOLO_MODEL_PATH",
             "SSA_VIDEO_1_PATH", "SSA_VIDEO_2_PATH", "SSA_VIDEO_3_PATH", "SSA_SQLITE_PATH",
             "SSA_FLASK_PROJECT_DIR", "SSA_FLASK_PYTHON_EXECUTABLE", "SSA_PDF_BROWSER_PATH",
             "YOLO_CONFIG_DIR", "XDG_CACHE_HOME", "TORCH_HOME"]


def capture(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    return result.returncode, result.stdout


def service_properties():
    code, output = capture(["systemctl", "show", "tomcat10", "--property=" + ",".join(SERVICE_KEYS)])
    if code:
        raise SystemExit("Cannot read tomcat10 service properties")
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def metadata(path):
    try:
        value = path.stat()
        result = {"path": str(path), "mode": oct(stat.S_IMODE(value.st_mode)),
                  "uid": value.st_uid, "gid": value.st_gid, "directory": path.is_dir(),
                  "symlink": path.is_symlink()}
        code, acl = capture(["getfacl", "-c", "-p", str(path)])
        result["acl"] = acl.strip().splitlines() if code == 0 else ["unavailable"]
        return result
    except OSError as error:
        return {"path": str(path), "error": type(error).__name__}


def identity(pid):
    fields = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key] = value.strip()
    return {"uid": int(fields["Uid"].split()[1]), "gid": int(fields["Gid"].split()[1]),
            "groups": list(map(int, fields["Groups"].split()))}


def environment(pid):
    # Captured only in memory; never serialize this dictionary into the report.
    raw = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    return dict(item.decode(errors="replace").split("=", 1) for item in raw if b"=" in item)


def paths_for(settings):
    upload = settings.get("SSA_UPLOAD_ROOT") or "/var/lib/project-ssa/uploads"
    cache = settings.get("SSA_CACHE_ROOT") or "/var/cache/project-ssa"
    result = [dict(name="spring_source", path=str(REPOSITORY / "project_ssa_spring"), directory=True),
              dict(name="flask_source", path=str(YOLO), directory=True),
              dict(name="flask_environment", path=str(YOLO / ".env")),
              dict(name="service_environment_root_only", path="/etc/project-ssa/tomcat.env", root_only=True),
              dict(name="python", path=str(YOLO / ".venv/bin/python"), executable=True),
              dict(name="python_resolved", path=str((YOLO / ".venv/bin/python").resolve()), executable=True),
              dict(name="flask_entry", path=str(YOLO / "run_server.py")),
              dict(name="upload", path=upload, directory=True, writable=True),
              dict(name="pdf_cache", path=str(Path(cache) / "pdf-cache/v4"), directory=True, writable=True),
              dict(name="cache_root", path=cache, directory=True, writable=True),
              dict(name="temporary", path="/tmp", directory=True, writable=True),
              dict(name="tomcat_logs", path="/var/log/tomcat10", directory=True, writable=True)]
    for category in ["member", "animals", "detection", "dangerlog"]:
        result.append(dict(name="upload_" + category, path=str(Path(upload) / category), directory=True, writable=True))
    for key in PATH_KEYS[2:]:
        value = settings.get(key, "")
        if value:
            if os.name != "nt" and (re.match(r"^[A-Za-z]:", value) or "://" in value):
                result.append(dict(name=key, invalid=True))
                continue
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = REPOSITORY / path
            directory = key in {"SSA_FLASK_PROJECT_DIR", "YOLO_CONFIG_DIR", "XDG_CACHE_HOME", "TORCH_HOME"}
            result.append(dict(name=key, path=str(path), directory=directory,
                               executable=key in {"SSA_FLASK_PYTHON_EXECUTABLE", "SSA_PDF_BROWSER_PATH"},
                               writable=key in {"SSA_SQLITE_PATH", "YOLO_CONFIG_DIR", "XDG_CACHE_HOME", "TORCH_HOME"}))
    return result


def access_probe(payload):
    os.setgroups(payload["identity"]["groups"])
    os.setgid(payload["identity"]["gid"])
    os.setuid(payload["identity"]["uid"])
    os.umask(int(payload["umask"], 8))
    if payload.get("cwd"):
        os.chdir(payload["cwd"])
    for key, value in payload.get("runtime_environment", {}).items():
        os.environ[key] = value
    results = []
    for item in payload["paths"]:
        value = {"name": item["name"]}
        if item.get("invalid"):
            results.append({**value, "status": "INVALID_OS_PATH"})
            continue
        if item.get("root_only"):
            results.append({**value, "status": "ROOT_READS_ENVIRONMENT_FILE"})
            continue
        path = Path(item["path"])
        try:
            exists = path.exists()
            value.update(exists=exists, read=os.access(path, os.R_OK),
                         write=os.access(path, os.W_OK), execute=os.access(path, os.X_OK))
            value["status"] = "OK" if exists and value["read"] and (
                not (item.get("directory") or item.get("executable")) or value["execute"]) and (
                not item.get("writable") or value["write"]) else "MISSING_OR_DENIED"
            if payload["verify"] and item.get("writable") and item.get("directory") and path.is_dir():
                probe = None
                try:
                    probe = path / (".ssa-permission-probe-" + uuid.uuid4().hex)
                    fd = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
                    os.write(fd, b"SSA disposable permission probe\n")
                    os.close(fd)
                    info = probe.stat()
                    value["write_probe"] = {"readback": probe.read_bytes() == b"SSA disposable permission probe\n",
                                            "gid": info.st_gid, "mode": oct(stat.S_IMODE(info.st_mode))}
                except OSError as error:
                    value["write_probe"] = {"error": type(error).__name__}
                finally:
                    if probe is not None:
                        probe.unlink()  # only this process's uniquely-created probe
        except OSError as error:
            value.update(status="INACCESSIBLE", error=type(error).__name__)
        results.append(value)
    scans = []
    if payload.get("full"):
        for root in [YOLO / "apps", YOLO / ".venv", REPOSITORY / "project_ssa_spring/src"]:
            bad, files, directories = [], 0, 0
            def on_error(error):
                if len(bad) < 30:
                    bad.append({"path": str(error.filename), "reason": type(error).__name__})
            for current, dirs, names in os.walk(root, followlinks=False, onerror=on_error):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                directories += 1
                if not os.access(current, os.R_OK | os.X_OK) and len(bad) < 30:
                    bad.append({"path": current, "reason": "directory_read_search"})
                for name in names:
                    files += 1
                    path = Path(current) / name
                    if not os.access(path, os.R_OK) and len(bad) < 30:
                        bad.append({"path": str(path), "reason": "file_read"})
            scans.append({"root": str(root), "files": files, "directories": directories, "denied_samples": bad})
    report = {"identity": {"uid": os.getuid(), "gid": os.getgid(), "groups": os.getgroups()},
            "paths": results, "trees": scans,
            "commands": {name: shutil.which(name) is not None for name in ["java", "mvn", "mpremote", "google-chrome", "chromium", "microsoft-edge"]},
            "mpremote_module": __import__("importlib.util", fromlist=["find_spec"]).find_spec("mpremote") is not None,
            "cuda_device_present": Path("/dev/dxg").exists()}
    report["stores"] = []
    for store in [row for row in payload["paths"] if row["name"] in {"upload", "cache_root"}]:
        root = Path(store["path"])
        total, denied, links = 0, 0, 0
        if root.is_dir():
            for current, directories, names in os.walk(root, followlinks=False):
                links += sum((Path(current) / name).is_symlink() for name in directories)
                for name in names:
                    path = Path(current) / name
                    if path.is_symlink():
                        links += 1
                        continue
                    total += 1
                    denied += not os.access(path, os.R_OK)
        report["stores"].append({"name": store["name"], "files": total, "unreadable_files": denied, "symlinks": links})
    if payload.get("oracle") or payload.get("verify_java"):
        deployed = Path("/var/lib/tomcat10/webapps/project_ssa_spring-0.0.1-SNAPSHOT/WEB-INF")
        command = ["java", "-DSSA_UPLOAD_ROOT=" + os.environ.get("SSA_UPLOAD_ROOT", "/var/lib/project-ssa/uploads"),
                   "-cp", str(deployed / "classes") + ":" + str(deployed / "lib/*") + ":/usr/share/tomcat10/lib/*",
                   str(Path(__file__).with_name("LinuxStorageProbe.java"))]
        if payload.get("oracle"):
            command.append("--oracle")
        if payload.get("verify_java"):
            command.append("--upload")
        code, output = capture(command, timeout=90)
        marker = "SSA_STORAGE_PROBE="
        rows = [row for row in output.splitlines() if row.startswith(marker)]
        report["java"] = json.loads(rows[-1][len(marker):]) if rows else {"exit_code": code, "error": "No structured Java probe result"}
    if payload.get("gpu"):
        import contextlib
        import hashlib
        import io
        try:
            settings = payload["runtime_environment"]
            model = Path(settings["SSA_YOLO_MODEL_PATH"])
            with model.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != "e04040d822c41e02346cf65539942905dff34ad5950e13baae065ed219df34f9":
                    raise ValueError("Unconfirmed checkpoint; GPU probe refused")
            def block_external(event, _args):
                if event in {"socket.connect", "subprocess.Popen"}:
                    raise PermissionError("External IO blocked in GPU probe")
            sys.addaudithook(block_external)
            os.environ.update(SSA_OPTIONAL_IO_ENABLED="false", SSA_AUTO_START_DETECTION_WORKERS="false",
                              SSA_SQLITE_PATH="", YOLO_AUTOINSTALL="false", YOLO_OFFLINE="true")
            sys.path.insert(0, str(YOLO))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                import cv2
                import torch
                from apps.app import create_app
                from apps.services import yolo_detector as detector
                app = create_app("ai")
                ai = detector.initialize_ai_runtime()
                videos = []
                for key in ["SSA_VIDEO_1_PATH", "SSA_VIDEO_2_PATH", "SSA_VIDEO_3_PATH"]:
                    capture_device = cv2.VideoCapture(settings[key])
                    try:
                        success, frame = capture_device.read()
                        if not success:
                            raise ValueError(key + " frame decode failed")
                        annotated, names, boxes = detector._run_inference(frame)
                        encoded, _data = cv2.imencode(".jpg", annotated)
                        videos.append({"setting": key, "decoded": True, "jpeg": bool(encoded), "detections": len(boxes)})
                    finally:
                        capture_device.release()
                report["gpu"] = {"aiReady": ai["ready"], "device": ai["device"],
                                 "gpu_name": torch.cuda.get_device_name(), "sqlite_engine": "sqlalchemy" in app.extensions,
                                 "videos": videos, "external_events": False}
                detector.shutdown_ai_runtime()
        except Exception as error:
            report["gpu"] = {"error_type": type(error).__name__, "settings": re.findall(r"SSA_[A-Z_0-9]+", str(error))}
    return report


def run_probe(payload, pid=None):
    command = [str(YOLO / ".venv/bin/python"), "-B", str(Path(__file__).resolve()), "--worker"]
    if pid:
        command = ["nsenter", "--target", str(pid), "--mount", "--"] + command
    result = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True, timeout=120)
    if result.returncode:
        return {"error": "Probe failed", "exit_code": result.returncode,
                "exception_types": re.findall(r"\b\w+(?:Error|Exception)\b", result.stderr)[-3:]}
    rows = [row for row in result.stdout.splitlines() if row.startswith("SSA_PERMISSION_PROBE=")]
    return json.loads(rows[-1].split("=", 1)[1]) if rows else {"error": "No structured worker result"}


def apply_permissions(settings, properties, deploy_war):
    upload = Path(settings.get("SSA_UPLOAD_ROOT") or "/var/lib/project-ssa/uploads")
    cache = Path(settings.get("SSA_CACHE_ROOT") or "/var/cache/project-ssa")
    # Deliberately bound the administrator operation to the reviewed runtime roots.
    if upload != Path("/var/lib/project-ssa/uploads") or cache != Path("/var/cache/project-ssa"):
        raise SystemExit("Configured runtime roots differ from reviewed plan; refusing to guess")
    for path in [upload, cache, *upload.parents, *cache.parents]:
        if path.is_symlink():
            raise SystemExit("Runtime path contains a symlink; review required")
    dropin = Path("/etc/systemd/system/tomcat10.service.d/ssa-runtime-permissions.conf")
    signature = "# Managed by Project SSA permission normalizer\n"
    if dropin.exists() and not dropin.read_text().startswith(signature):
        raise SystemExit("Unrecognized drop-in exists; refusing to overwrite")
    sqlite_dropin = dropin.with_name("ssa-flask-sqlite.conf")
    if sqlite_dropin.exists() and (sqlite_dropin.read_text().strip() != "[Service]\nReadWritePaths=/var/lib/project-ssa/flask"
                                  or sqlite_dropin.with_suffix(".conf.disabled").exists()):
        raise SystemExit("SQLite service settings differ from reviewed plan")
    base = settings.get("SSA_FLASK_STREAM_URL", "http://localhost:5000/stream").rstrip("/")
    from urllib.parse import urlsplit
    if urlsplit(base).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Remote Flask target: graceful shutdown requires separate review")
    try:
        with urllib.request.urlopen(base + "/health", timeout=3) as response:
            health = json.load(response)
    except urllib.error.URLError:
        health = None
    if health is not None:
        token = settings.get("SSA_FLASK_CONTROL_TOKEN", "")
        request = urllib.request.Request(base + "/admin/shutdown", method="POST",
                                         headers={"X-SSA-Flask-Control-Token": token})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status != 200:
                    raise SystemExit("Flask graceful stop refused")
        except Exception:
            raise SystemExit("Flask graceful stop failed; no permissions changed") from None
        pid = str(health.get("instanceId", ""))
        if not pid.isdigit():
            raise SystemExit("Cannot identify stopped Flask; inspect before continuing")
        deadline = time.monotonic() + 20
        while Path("/proc", pid).exists() and time.monotonic() < deadline:
            time.sleep(.2)
        if Path("/proc", pid).exists():
            raise SystemExit("Flask process has not exited; no forced termination performed")
    backup = Path(tempfile.mkdtemp(prefix="project-ssa-permissions.", dir="/var/backups"))
    backup.chmod(0o700)
    directories = [upload] + [upload / category for category in ["member", "animals", "detection", "dangerlog"]]
    directories += [cache, cache / "pdf-cache", cache / "pdf-cache/v4", cache / "ai", cache / "ai/Ultralytics"]
    existing = [path for path in directories if path.exists()]
    if existing:
        code, acl = capture(["getfacl", "-p", *map(str, existing)])
        if code:
            raise SystemExit("Cannot snapshot ACLs")
        (backup / "directory-acls.txt").write_text(acl)
    (backup / "created-directories.json").write_text(json.dumps([str(p) for p in directories if not p.exists()]))
    group = grp.getgrnam("ssa-upload").gr_gid
    user = pwd.getpwnam("tomcat").pw_uid
    for directory in directories:
        if directory.is_symlink():
            raise SystemExit("Storage category is a symlink; manual review required")
        created = not directory.exists()
        directory.mkdir(mode=0o2770, parents=True, exist_ok=True)
        if created:
            os.chown(directory, user, group)
        elif directory.stat().st_gid != group:
            raise SystemExit("Existing directory group differs; manual review required")
        directory.chmod(stat.S_IMODE(directory.stat().st_mode) | stat.S_ISGID)
        subprocess.run(["setfacl", "-m", "u:tomcat:rwx,g:ssa-upload:rwx,m::rwx", str(directory)], check=True)
        subprocess.run(["setfacl", "-d", "-m", "u::rwx,u:tomcat:rwx,g::rwx,g:ssa-upload:rwx,m::rwx,o::---", str(directory)], check=True)
    if dropin.exists():
        shutil.copy2(dropin, backup / dropin.name)
    if sqlite_dropin.exists():
        expected = "[Service]\nReadWritePaths=/var/lib/project-ssa/flask"
        if sqlite_dropin.read_text().strip() != expected:
            raise SystemExit("SQLite drop-in changed; refusing to modify custom settings")
        disabled = sqlite_dropin.with_suffix(".conf.disabled")
        if disabled.exists():
            raise SystemExit("SQLite disabled drop-in already exists; review required")
        shutil.copy2(sqlite_dropin, backup / sqlite_dropin.name)
        sqlite_dropin.rename(disabled)  # preserve file and DB; AI mode needs no SQLite writes
    dropin.write_text(signature + "[Service]\nSupplementaryGroups=ssa-upload\nUMask=0007\n"
                      "ReadWritePaths=/var/lib/project-ssa/uploads /var/cache/project-ssa\n"
                      "Environment=SSA_FLASK_PROFILE=ai\nEnvironment=SSA_CACHE_ROOT=/var/cache/project-ssa\n"
                      "Environment=YOLO_CONFIG_DIR=/var/cache/project-ssa/ai\n")
    dropin.chmod(0o644)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    if deploy_war:
        subprocess.run(["bash", str(Path(__file__).with_name("deploy-tomcat-java17.sh")), "--apply"], check=True)
    else:
        subprocess.run(["systemctl", "restart", "tomcat10"], check=True)
    subprocess.run(["systemctl", "is-active", "--quiet", "tomcat10"], check=True)
    ready = False
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8080/project_ssa_spring-0.0.1-SNAPSHOT/", timeout=2) as response:
                ready = response.status == 200
            if ready and deploy_war:
                relative = "com/spring/util/MultipartFileUpload.class"
                built = REPOSITORY / "project_ssa_spring/target/classes" / relative
                deployed = Path("/var/lib/tomcat10/webapps/project_ssa_spring-0.0.1-SNAPSHOT/WEB-INF/classes") / relative
                ready = built.read_bytes() == deployed.read_bytes()
            if ready:
                break
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.5)
    if not ready:
        raise SystemExit("Tomcat started but updated Spring app is not ready; inspect backup and logs")
    print("Applied reviewed runtime permissions; backup:", backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="create/read/delete unique probe files only")
    parser.add_argument("--full", action="store_true", help="scan source and venv metadata as service identity")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true", help="apply reviewed runtime-only ACL/systemd changes")
    parser.add_argument("--deploy-war", action="store_true", help="with --apply, deploy the verified upload permission fix")
    parser.add_argument("--oracle", action="store_true", help="read-only Oracle SELECT and image reference counts")
    parser.add_argument("--gpu", action="store_true", help="trusted model CUDA and local video inference, no events")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print("SSA_PERMISSION_PROBE=" + json.dumps(access_probe(json.load(sys.stdin))))
        return
    if args.report and args.report.exists():
        raise SystemExit("Report already exists; select a new report filename before making changes")
    if args.deploy_war and not args.apply:
        raise SystemExit("--deploy-war requires explicit --apply")
    if os.geteuid() != 0:
        raise SystemExit("Read-only service audit requires sudo for /proc and mount namespace access")
    from dotenv import dotenv_values
    properties = service_properties()
    pid = int(properties["MainPID"])
    if not pid:
        raise SystemExit("Tomcat is not running; namespace verification is unavailable")
    process_environment = environment(pid)
    local = {key: value for key, value in dotenv_values(YOLO / ".env").items() if value is not None}
    effective = {**local, **process_environment}
    # RuntimeSettings gives explicit JVM -D properties priority over the environment.
    for arg in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0"):
        if arg.startswith(b"-D") and b"=" in arg:
            key, value = arg[2:].decode(errors="replace").split("=", 1)
            if key in PATH_KEYS:
                effective[key] = value
    if args.apply:
        apply_permissions(effective, properties, args.deploy_war)
        properties = service_properties()
        pid = int(properties["MainPID"])
        process_environment = environment(pid)
        effective = {**local, **process_environment}
    paths = paths_for(effective)
    parent_paths = set()
    for item in paths:
        if "path" in item:
            path = Path(item["path"])
            parent_paths.add(path)
            parent_paths.update(path.parents)
    payload = {"paths": paths, "identity": identity(pid), "umask": properties.get("UMask", "0022"),
               "verify": args.verify, "full": args.full, "oracle": args.oracle,
               "verify_java": args.verify, "gpu": args.gpu,
               "cwd": os.readlink(f"/proc/{pid}/cwd"),
               "runtime_environment": {key: effective[key] for key in PATH_KEYS + ["HOME", "PATH", "TMPDIR", "LD_LIBRARY_PATH"] if effective.get(key)}}
    # Legacy data are preserved, but an AI-only process must not need SQLite writes.
    for item in paths:
        if item["name"] == "SSA_SQLITE_PATH" and effective.get("SSA_FLASK_PROFILE", "ai") == "ai":
            item["writable"] = False
    # Match the actual child's inherited PATH when testing executable discovery.
    os.environ["PATH"] = process_environment.get("PATH", os.defpath)
    report = {"service": properties, "configured_path_keys": {key: key in effective for key in PATH_KEYS},
              "selected_flask_profile": effective.get("SSA_FLASK_PROFILE", "ai") if effective.get("SSA_FLASK_PROFILE", "ai") in {"ai", "local", "testing"} else "invalid",
              "paths": paths, "metadata": [metadata(p) for p in sorted(parent_paths)],
              "host_as_service_user": run_probe(payload), "service_mount_namespace": run_probe(payload, pid),
              "missing_required_settings": [key for key in ["SSA_YOLO_MODEL_PATH", "SSA_VIDEO_1_PATH", "SSA_VIDEO_2_PATH", "SSA_VIDEO_3_PATH", "SSA_FLASK_PROJECT_DIR", "SSA_FLASK_PYTHON_EXECUTABLE"] if not effective.get(key)],
              "spring_flask_upload_consistent": (process_environment.get("SSA_UPLOAD_ROOT") or "/var/lib/project-ssa/uploads") == (effective.get("SSA_UPLOAD_ROOT") or "/var/lib/project-ssa/uploads"),
              "secret_presence": {key: bool(effective.get(key)) for key in ["SSA_FLASK_CONTROL_TOKEN", "DISCORD_WEBHOOK_URL"]}}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(output + "\n")
        print("Sanitized permission report:", args.report)
        for context in ["host_as_service_user", "service_mount_namespace"]:
            rows = report[context].get("paths", [])
            print(context, "issues:", [(row["name"], row["status"]) for row in rows if row["status"] not in {"OK", "ROOT_READS_ENVIRONMENT_FILE"}])
    else:
        print(output)


if __name__ == "__main__":
    main()
