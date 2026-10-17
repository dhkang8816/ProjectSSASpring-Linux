# Python test guide

## Current GPU environment verification

The project `.venv` now contains the real runtime dependencies, including
PyTorch 2.7.1+cu126 / torchvision 0.22.1+cu126 / Ultralytics 8.4.54. The suite
passes **88 tests** with automatic detection workers disabled; no Ultralytics
import stub is used in this run. The new device/readiness tests mock models and
hardware explicitly. Existing test files also cover health readiness without a control token,
mocked danger-event callback/notification worker flow, snapshot failure text alerts,
and webhook-safe error logging. `pip check` reports no broken requirements.

`test_stream_health.py` also checks that the AI profile starts with an empty
SQLite setting and no SQLAlchemy/Migrate engine while the legacy testing profile
keeps its DB and UI blueprints. `test_runtime_paths.py` verifies disposable
permission probes preserve existing files. The separate Java-controlled real
Flask lifecycle and four-channel GPU checks now select `ai` with no SQLite DB.
The administrator audit also verified CUDA and all three actual video inputs
as `tomcat` inside the running service's mount namespace. See
[the runtime permission report](../LINUX_RUNTIME_PERMISSIONS.md) for scope.

Real CUDA tensor/model inference, four concurrent MJPEG test clients, and the
Java-controlled Flask lifecycle were checked separately. See
[GPU_ENVIRONMENT_LINUX.md](GPU_ENVIRONMENT_LINUX.md) for commands and limits.
Older temporary-environment results below describe the earlier path-only audit.

Run the tests with the project virtual environment:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests -q -p no:cacheprovider
```

Linux, from `project_ssa_yolo`:

```bash
SSA_AUTO_START_DETECTION_WORKERS=false PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m pytest tests -q -p no:cacheprovider
```

Set `SSA_AUTO_START_DETECTION_WORKERS=false` on Windows as well when a local
`.env` enables automatic workers. The project `.env` is loaded before config
imports; process environment settings take priority. Do not point
`SSA_TEST_SQLITE_PATH` at production data.

The test suite mocks subprocess, HTTP and Flask state. It does not open COM6,
run YOLO inference, send Discord notifications or require an ESP32 board.

`requirements-test.txt` installs `requirements.txt` first and then adds pytest.
`requirements-ai.txt` is an optional reduced runtime list; it does not install
the legacy SQLAlchemy/Migrate/pandas dependencies. Existing installed packages
and the validated CUDA lock file were preserved.

`test_runtime_paths.py` covers project-relative resolution, invalid OS paths,
missing files, upload permissions, external SQLite and failed snapshot writes.
`test_training_paths.py` uses temporary files and a mock model, never training.
These checks do not establish that PyTorch/CUDA, real weights or USB devices
are available. See [the path audit](../PATH_CONFIGURATION_LINUX.md).

The earlier 2026-10-17 path-only verification used a separate Python 3.11 environment under `/tmp`,
without changing the application's virtual environment or runtime requirements:

- Path/training/buzzer/read-only-inspector tests: **41 passed**, using the normal test modules.
- Full own-project suite: **68 passed** under an additional temporary harness.
  The harness disabled automatic workers and startup/shutdown sounds, blocked
  socket connections, real subprocesses, database connections and VideoCapture,
  and supplied an Ultralytics import stub whose constructor fails if used.
  OpenCV's headless package provided real JPEG encode/decode tests. PyTorch and
  Ultralytics were not installed in this temporary environment, so this is a
  unit regression result rather than runtime dependency/inference validation.
- Syntax parsing: 44 own-project Python files, 0 errors; vendor/board code was
  not treated as the host application's test suite.

The focused command, run from `project_ssa_yolo`, was:

```bash
python -B -m pytest tests/test_runtime_paths.py tests/test_training_paths.py \
  tests/test_buzzer_helper.py tests/test_path_check.py -q -p no:cacheprovider
```
