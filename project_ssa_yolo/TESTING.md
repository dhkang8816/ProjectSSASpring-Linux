# Python test guide

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

`test_runtime_paths.py` covers project-relative resolution, invalid OS paths,
missing files, upload permissions, external SQLite and failed snapshot writes.
`test_training_paths.py` uses temporary files and a mock model, never training.
These checks do not establish that PyTorch/CUDA, real weights or USB devices
are available. See [the path audit](../PATH_CONFIGURATION_LINUX.md).

2026-10-17 verification used a separate Python 3.11 environment under `/tmp`,
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
