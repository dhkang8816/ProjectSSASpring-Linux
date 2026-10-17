# Linux / WSL2 커스텀 YOLO GPU 실행 환경

## 확인한 환경과 버전

2026-10-17 사용자 확인을 받은 기존 커스텀 `yolov8n_train-6/weights/best.pt`로 검증했다. 기존 가중치·영상·SQLite·실제 `.env`·JDBC 설정은 변경하지 않았다. 시스템 패키지, Windows/Linux 드라이버, CUDA Toolkit, 운영 Tomcat 서비스 설정도 변경하지 않았다.

| 항목 | 설치/검증 결과 |
| --- | --- |
| Linux | Ubuntu 26.04.1 LTS, WSL2 kernel `6.18.54.1-microsoft-standard-WSL2` |
| Python | **3.11.17**, `project_ssa_yolo/.venv`; 시스템 Python 3.14.4는 변경하지 않음 |
| pip / venv | 가상환경 pip 24.0, 기존 Python 3.11의 venv/ensurepip 사용 |
| PyTorch | **2.7.1+cu126** |
| torchvision | **0.22.1+cu126** |
| PyTorch CUDA runtime | **12.6** |
| Ultralytics | **8.4.54**, 체크포인트에 기록된 버전과 일치 |
| NumPy / OpenCV | **2.2.6 / opencv-python 4.13.0.92** (`cv2.__version__`은 4.13.0) |
| Flask / mpremote | 3.1.3 / 1.29.0; 실제 mpremote 장치 통신은 미검증 |
| GPU | **NVIDIA GeForce RTX 3080, 10 GB**, CUDA tensor 연산 및 커스텀 추론 성공 |
| Windows 드라이버 | NVIDIA KMD **617.42**. `nvidia-smi`의 CUDA UMD 13.4 표시는 설치한 Toolkit 버전이 아님 |

Python 3.11은 기존 프로젝트 기준과 선택한 PyTorch wheel 조합에 맞춘 것이다. 최신 버전으로 일괄 변경하지 않았다. 핵심 버전은 `constraints-linux-cu126.txt`, 실제 설치한 전이 의존성까지 포함한 스냅샷은 `requirements-linux-cu126.lock.txt`에 고정했다. 스냅샷에는 검증용 pytest도 포함된다.

PyTorch/torchvision 조합과 다운로드 주소는 [공식 이전 버전 설치 안내](https://pytorch.org/get-started/previous-versions/)의 CUDA 12.6 조합을 사용했다. WSL은 [NVIDIA WSL 안내](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)에 따라 Windows 호스트 드라이버를 사용한다. Linux GPU 드라이버나 드라이버 포함 CUDA 메타패키지를 설치하지 않는다.

현재 시스템의 libGL/libglib/libgthread는 존재하며 원래 `opencv-python` wheel import와 영상 디코딩이 성공했다. gcc/g++, ffmpeg CLI, nvcc는 확인되지 않았지만 이번 wheel 기반 추론에는 필요하지 않았다. 별도 CUDA Toolkit, 컴파일러, FlashAttention은 설치하지 않았다. 다른 환경에서 OS 라이브러리가 누락되면 먼저 오류·필요 패키지를 확인하고 시스템 설치 승인을 받아야 한다.

## 동일 환경 설치 명령

저장소 루트에서 실행한다. 이미 있는 `.venv`를 삭제하거나 덮어쓰지 말고 기존 버전을 먼저 확인한다. 다음 명령은 운영 서비스 설정을 변경하지 않는다.

```bash
python3.11 -m venv project_ssa_yolo/.venv
project_ssa_yolo/.venv/bin/python -m pip install \
  torch==2.7.1 torchvision==0.22.1 \
  --index-url https://download.pytorch.org/whl/cu126
project_ssa_yolo/.venv/bin/python -m pip install \
  -r project_ssa_yolo/requirements-linux-cu126.lock.txt
project_ssa_yolo/.venv/bin/python -m pip check
```

기존 requirements와 핵심 제약으로 다시 검증하려면 다음 명령을 사용한다. 전이 의존성까지 정확한 재현에는 위 lock 파일을 사용한다.

```bash
project_ssa_yolo/.venv/bin/python -m pip install \
  -r project_ssa_yolo/requirements.txt \
  -c project_ssa_yolo/constraints-linux-cu126.txt
```

`pip check`는 충돌 없음으로 통과했다. vendor `yolov12/requirements.txt`의 PyTorch 2.2.2/FlashAttention 조합은 별도 학습 소스용이며 이번 YOLOv8n 런타임 환경에 섞어 설치하지 않았다.

## 유지한 커스텀 모델

- 파일: `project_ssa_yolo/runs/detect/my_yolov12_project/yolov8n_train-6/weights/best.pt`
- SHA-256: `e04040d822c41e02346cf65539942905dff34ad5950e13baae065ed219df34f9`
- 실제 구조: **커스텀 YOLOv8n detect**, C2f/SPPF 및 stock Ultralytics DetectionModel/Detect. 학습 인자의 `model: yolov8n.pt`와 정적 pickle 전역 참조를 먼저 확인했다.
- GPU 로딩/추론 후 파라미터 수: 3,006,818. 체크포인트의 Ultralytics 버전은 8.4.54다.
- 원래 학습 시 PyTorch 버전은 체크포인트에 기록되어 있지 않았고 기존 환경의 설치 메타데이터도 발견하지 못했다. 여기의 PyTorch 2.7.1은 실제 Linux 호환성 검증 결과이며 원래 Windows 버전이었다고 주장하지 않는다.
- 선택 모델에는 별도의 사용자 Python 레이어/FlashAttention이 필요하지 않았다. 다른 YOLO12/YOLOv5 가중치는 로딩·대체하지 않았다.

| 체크포인트 class ID | 이름 | 기존 Spring 이벤트 도메인 코드 |
| --- | --- | --- |
| 0 | blue_alien | 2 |
| 1 | blue_shark | 3 |
| 2 | pink_dragon | 4 |
| 3 | cat | 1 |
| 4 | dog | 0 |
| 5 | tiger | 5 |

도메인 코드는 모델 class ID가 아니라 기존 `YOLO_TO_CODE`의 이름 매핑을 유지한다. 탐지 이벤트/Oracle payload와 정책 로직을 변경하지 않았다. 실제 Oracle 저장은 이번에 실행하지 않았다.

`.pt`는 역직렬화 시 코드를 포함할 수 있으므로 출처를 확인해야 한다. 이번에는 사용자가 소유·확인한 기존 파일을 정적 분석한 후 해시가 일치하는 파일만 GPU 검사에 사용했다. 해시 계산만으로 출처의 신뢰성이 생기지는 않는다. 진단 도구는 `--sha256` 불일치 시 로딩을 거부하며 임의 가중치를 다운로드하지 않는다.

## 실행 설정과 준비 상태

실제 `.env`와 Tomcat 환경변수 파일은 자동 편집하지 않았다. 설정은 실행 프로세스 환경변수로 덮어쓸 수 있다. 경로 기준과 저장소 준비는 [전체 경로 안내](../PATH_CONFIGURATION_LINUX.md)를 따른다.

| 변수 | 설정 계약 |
| --- | --- |
| `SSA_YOLO_MODEL_PATH` | 사용자가 확인한 기존 커스텀 파일. 기본 모델 다운로드/대체 없음 |
| `SSA_YOLO_DEVICE` | 기본 `cuda:0`. `cuda`, GPU 번호, `cuda:N` 지원. CUDA 불가/잘못된 번호는 오류. CPU는 **명시적으로 `cpu`**를 지정할 때만 사용 |
| `SSA_VIDEO_1_PATH`, `SSA_VIDEO_2_PATH`, `SSA_VIDEO_3_PATH` | 기존 영상 파일을 명시. 현재 로컬 설정은 Linux 절대경로이며 세 파일의 존재·개발 계정 읽기 권한을 확인함. 실제 값은 출력하지 않음 |
| `SSA_SQLITE_PATH` | 기존 운영 SQLite 파일을 명시. 미설정/부재 시 Flask 시작 실패, 빈 운영 DB 생성 안 함 |
| `SSA_UPLOAD_ROOT`, `SSA_CACHE_ROOT` | 기존 경로 안내의 기본값/재정의 사용. 운영 디렉터리·공유 권한은 별도 승인 후 준비 |
| `SSA_OPTIONAL_IO_ENABLED` | 기본 true. false이면 USB sensor/buzzer 및 Discord 알림 worker를 시작하지 않음. GPU 초기화는 별도로 검증. 이 값만으로 영상 탐지 이벤트의 Spring callback까지 차단되는 것은 아님 |
| `SSA_AUTO_START_DETECTION_WORKERS` | 기본 false. 프로세스 시작/AI 초기화가 실제 카메라 시작을 의미하지 않음 |
| `YOLO_CONFIG_DIR` | Ultralytics 설정을 둘 **기존의 쓰기 가능한 상위 디렉터리**. 라이브러리는 그 아래 `Ultralytics`를 사용. 테스트는 `/tmp` 사용. 운영 위치는 승인 후 지정 |
| `YOLO_OFFLINE`, `YOLO_AUTOINSTALL` | 앱은 기본적으로 true/false를 사용해 Ultralytics 온라인 확인·자동 설치를 막는다. Spring callback 등 별도 requests 연동과는 무관 |
| `SSA_FLASK_PROJECT_DIR`, `SSA_FLASK_PYTHON_EXECUTABLE` | Tomcat에 Python 모듈 루트와 `.venv/bin/python`의 절대경로 설정 |
| `SSA_FLASK_STREAM_URL`, `SSA_FLASK_CONTROL_ENABLED`, `SSA_FLASK_CONTROL_TOKEN` | 기존 로컬 시작·종료 제어 설정. 양쪽 토큰 일치 필요, 값은 출력하지 않음 |

사용자가 확인한 파일을 실행 셸에서 선택하는 예시는 다음과 같다. 운영 모델을 복사하거나 `.env`를 수정하는 명령이 아니다. SQLite·영상·장비 주소는 별도로 실제 값을 준비해야 한다.

```bash
# 저장소 루트에서
export SSA_YOLO_MODEL_PATH="$PWD/project_ssa_yolo/runs/detect/my_yolov12_project/yolov8n_train-6/weights/best.pt"
export SSA_YOLO_DEVICE=cuda:0
# SSA_SQLITE_PATH, SSA_VIDEO_1_PATH~3_PATH 등 실제 설정을 완료한 뒤:
project_ssa_yolo/.venv/bin/python project_ssa_yolo/run_server.py
```

`/stream/health`는 캐시된 상태만 읽는다. 실제 AI 초기화는 토큰으로 보호된 `/stream/admin/initialize` 또는 채널 시작에서 수행한다. 초기화는 **CUDA 텐서 연산 → 기존 커스텀 모델 로드 → 실제 워밍업 추론 → 모델 장치 확인**을 통과해야 한다. 검은 테스트 프레임의 워밍업은 이벤트를 발생시키지 않는다. 준비 상태의 `ready`, `aiReady`, `processReady`를 구분한다.

Spring `FlaskRuntimeControlService`는 HTTP 200만으로 AI 준비를 선언하지 않고 Flask의 `aiReady`를 확인한다. JSP 버튼도 프로세스 ON과 AI 준비/미준비를 구분하며 실패 원인을 표시한다. 기존 단일 모델 `_model`과 `_model_inference_lock`을 유지했고 네 worker가 그 모델을 공유한다.

종료 시 capture 소유 worker를 먼저 join한 뒤 모델 참조와 CUDA allocator cache를 해제한다. 프로세스 종료 전 cuBLAS workspace는 남을 수 있다. 실제 검증에서는 모델 해제 후 8.125 MiB가 남았으며, **진단 프로세스에서만** private cuBLAS workspace 해제를 시도했을 때 0 MiB가 되어 원인을 확인했다. 제품 코드는 이 private API를 사용하지 않는다. 정상 Flask 프로세스 종료까지 별도로 확인했다.

## 실제 검증 결과

| 검증 | 결과와 범위 |
| --- | --- |
| NVIDIA / CUDA | RTX 3080 10GB 인식, CUDA 텐서 행렬 연산 성공 |
| 단일 이미지 | 로컬 `streaming_0.mp4` 첫 프레임으로 실제 GPU 추론 성공, 2개 탐지 |
| 단일 추론 시간 | 워밍업 후 10회 평균 약 **9.7~10.7 ms**. 전체 서비스 지연과 다름 |
| 4 worker | 로컬 영상 3개와 로컬 영상으로 모의한 ESP32, **모델 생성 1회** |
| 동시 MJPEG | Flask test client **4개 동시 연결**, 네 채널 모두 JPEG frame/HTTP 200 |
| 처리량 | 3초 표본에서 채널당 약 **19~20 FPS**, 최근 frame 처리 약 **13.6~26.8 ms**. GPU lock 대기·추론·후처리 포함, 실제 카메라 end-to-end 지연 아님 |
| GPU allocator | 네 채널 운용 시 allocated 약 **25.7~26.3 MiB**, reserved **60 MiB**. 드라이버/다른 앱까지 포함한 전체 VRAM 사용량은 아님 |
| 종료 | 네 worker/capture 종료 확인. 모델·cache 해제 및 별도 실제 Flask 프로세스 종료 확인 |
| Spring 자동 실행 | 실제 Java 서비스가 프로젝트 `.venv`의 Flask를 임시 loopback 포트로 시작, GPU AI 준비 확인, 중복 시작 거부, 토큰 종료 후 자식 프로세스 종료 확인 |
| 회귀 검사 | 실제 런타임 의존성으로 Python **78 passed**, `pip check` 충돌 없음. Java `mvn -o verify` **118 tests, 0 failures/errors, 1 Windows-only skip**, GPU 통합 검사 포함 |

4채널 검사는 Oracle metadata/event와 알림 경로를 mock하고 외부 socket/subprocess 연결을 차단했다. ESP32-CAM은 실제 장비가 아니라 동일 reader 인터페이스의 로컬 영상 adapter다. 이 결과를 실제 ESP32/Oracle/운영 Spring 화면의 통합 검증으로 해석하지 않는다. 짧은 표본이므로 장시간 안정성/메모리 증가/실제 네트워크 지연은 별도 검사 대상이다.

## 재검증 명령

저장소 루트에서 사용자 확인 모델의 해시를 명시한다. 모든 모델 검사는 GPU를 사용하며 운영 Tomcat에 배포하지 않는다.

```bash
YOLO_CONFIG_DIR=/tmp YOLO_AUTOINSTALL=false project_ssa_yolo/.venv/bin/python -B \
  project_ssa_yolo/scripts/diagnostics/gpu_preflight.py \
  --model "$SSA_YOLO_MODEL_PATH" \
  --sha256 e04040d822c41e02346cf65539942905dff34ad5950e13baae065ed219df34f9 \
  --video project_ssa_yolo/videos/streaming_0.mp4

YOLO_CONFIG_DIR=/tmp YOLO_AUTOINSTALL=false project_ssa_yolo/.venv/bin/python -B \
  project_ssa_yolo/scripts/diagnostics/gpu_four_channel_check.py \
  --model "$SSA_YOLO_MODEL_PATH" \
  --sha256 e04040d822c41e02346cf65539942905dff34ad5950e13baae065ed219df34f9 \
  --videos project_ssa_yolo/videos/streaming_0.mp4 \
           project_ssa_yolo/videos/streaming_3.mp4 project_ssa_yolo/videos/streaming_2.mp4

python3 project_ssa_spring/scripts/check-flask-gpu.py \
  --model "$SSA_YOLO_MODEL_PATH" \
  --sha256 e04040d822c41e02346cf65539942905dff34ad5950e13baae065ed219df34f9
```

마지막 도구는 임시 테스트 SQLite/제어 토큰/loopback 포트를 사용하고 장치·알림 worker를 비활성화한다. 기존 운영 DB와 토큰을 사용하거나 수정하지 않는다. 일반 Maven 검사에서는 실제 GPU 통합 테스트를 기본 skip한다. 실제 실행은 `SSA_RUN_GPU_INTEGRATION=true`를 지정한 격리 도구가 담당한다.

Codex 샌드박스에서는 `/dev/dxg`가 보이지 않고 NVML이 OS 차단 오류를 반환했다. 승인된 샌드박스 외부 검사에서는 GPU 접근과 추론이 성공했다. 이 제한을 WSL 드라이버 고장으로 오인해 Linux 드라이버를 설치하지 않는다.

## 운영 반영 전에 남은 작업

이전 경로 점검 이후 이번 GPU 요청 전에 업로드 디렉터리와 실제 `.env`가 이미 변경되어 있었다. 현재 업로드 저장소는 존재하며 `root:ssa-upload`, 2770으로 확인했다. 이 기존 상태를 유지했고 값·권한을 되돌리지 않았다. PDF 캐시 루트는 아직 없다. GPU 환경 구성 당시 모델·운영 SQLite 변수는 미설정이었다. 이후 사용자 승인으로 기존 파일 경로 두 변수를 설정한 내용은 아래 영상 연동 진단 기록을 참고한다.

- 운영 Tomcat WAR 교체/재시작은 하지 않았다. Spring 관리 화면과 실제 ESP32-CAM을 포함하는 4채널 관제는 아직 미검증이다.
- 현재 `tomcat` 계정은 개발자 홈 디렉터리의 검색 권한이 없어 이 저장소와 홈 아래 Python 3.11 기본 인터프리터에 접근할 수 없다. `.venv`는 그 인터프리터를 참조하므로 폴더만 복사해서 해결된다고 가정하지 않는다. 서비스 계정 경로/설치·권한 계획은 승인 후 적용해야 한다.
- 현재 서비스는 `ProtectSystem=strict`, `PrivateTmp=yes`, `NoNewPrivileges=true`다. 업로드/PDF cache/Ultralytics 설정 쓰기 허용과 GPU 장치·라이브러리 접근을 **실제 서비스 계정/namespace**에서 확인해야 한다. 개발 계정 통합 검사가 이를 대신하지 않는다.
- 실제 모델·영상·SQLite 경로와 Spring/Flask URL·토큰은 운영자가 준비해야 한다. 이 작업에서 `.env`, JDBC, Windows 네트워크/방화벽, 서비스 환경변수를 변경하지 않았다.
- 실제 Oracle 저장·Discord 전송·USB 부저/센서·실제 ESP32 스트림·장시간 4채널 브라우저 관제는 별도 승인·설정 후 검증한다.


## 영상 연동 후 상태·알림 진단 및 수정 (2026-10-17)

### 수정 전 확인한 근거

- 조사 시점에는 Tomcat 8080만 실행 중이고 Flask 5000 listener/Python 서버 프로세스는 없었다. 따라서 사용자가 영상을 보던 시점의 health 응답, 실행 환경변수, 초기화 로그를 직접 확보하지 못했다. 현재 중복 Flask 프로세스는 발견하지 못했지만 과거 중복 실행 여부를 배제하는 증거는 아니다.
- `/stream/health`는 `ai.ready`를 제공하지만 최상위 `processReady`/`aiReady`/`ready`는 제공하지 않았다. Spring은 HTTP 상태로 process online을 판단한 후, AI 상태에는 제어 토큰이 필요한 `/stream/admin/startup-status`를 별도로 사용했다. 토큰 미설정·불일치 시 실제 모델 상태와 무관하게 AI 미준비가 표시되는 경로가 있었다. 당시 토큰 불일치가 실제 발생했다고 단정하지 않는다.
- `SSA_SPRING_HOST`의 코드 기본값이 `/`로 끝나고 oracle_service가 `/yolo/...`, `/api/...`를 추가해 이중 슬래시를 만들었다. 실제 로컬 Tomcat에 읽기 전용 metadata GET을 보내 정상 경로 HTTP 200, 이중 슬래시 경로 HTTP 400을 확인했다. 로컬 `.env`에는 이 변수의 재정의가 없지만, 중지된 Flask가 실행 시 상속한 환경변수는 확인할 수 없었다.
- 현재 개발 프로세스는 업로드 루트에 읽기·쓰기·검색 권한이 없다. 계정은 공유 `ssa-upload` 그룹에 **등록**되어 있지만 현재 프로세스의 **유효 그룹**에 없다. 기존 보고 함수는 스냅샷 저장을 Discord enqueue보다 먼저 실행하므로 저장 권한 오류가 나면 두 후속 처리 모두 중단됐다. 당시 Flask의 실행 계정/그룹은 미확인이다. 디렉터리 소유권·권한·사용자 그룹 설정은 변경하지 않았다.
- 로컬 webhook은 설정되어 있다. 실제 값은 열람 결과·문서·로그에 출력하지 않았다. `SSA_OPTIONAL_IO_ENABLED`는 로컬 `.env`에 없어서 코드 기본값은 true지만, 과거 실행 셸의 덮어쓰기는 확인되지 않았다.
- Spring callback 경로 `/yolo/api/**`는 현재 Security 설정상 별도 브라우저 인증/제어 토큰을 요구하지 않는다. 읽기 metadata와 매핑 경로도 공개되어 있다. Flask 제어 토큰은 시작·초기화·종료용이며 callback 인증 토큰과 혼동하지 않는다. 방화벽·Oracle·Security 규칙은 변경하지 않았다.

### 수정한 동작

- health와 보호된 startup-status가 같은 캐시 상태 생성 함수를 공유한다. health 조회는 초기화, worker 시작, 추론, 알림을 실행하지 않는다. `processReady`는 HTTP 프로세스, `aiReady`는 실제 CUDA 확인·모델 로딩·워밍업 완료, `ready`는 AI와 부가 서비스 초기화 완료를 뜻한다. 부가 서비스가 비활성화된 경우에도 그 설정에 따른 시작 절차가 완료되면 servicesStarted가 true가 될 수 있다.
- Spring의 정기 상태 조회는 health의 실제 AI 상태를 읽는다. 기존 health 형식의 `ai.ready`도 지원하되 필드 부재/실패를 성공으로 간주하지 않는다. 시작·초기화·종료는 계속 토큰으로 보호한다. `instanceId`는 Flask PID이며 한 시점의 인스턴스 비교용이다(PID 재사용 가능).
- health와 Spring 상태 응답은 `Cache-Control: no-store`, JSP fetch도 `cache: no-store`를 사용한다. 기존 3초 정기 조회와 시작 중 0.5초 조회는 유지한다. 캐시가 기존 증상의 실제 원인이었다고 단정하지 않는다.
- Spring base URL의 끝 슬래시만 정리한다. 라우트·JDBC·장비 주소는 변경하지 않는다. 보고 POST는 HTTP 200뿐 아니라 JSON `status: SUCCESS`도 확인해 로그인 HTML을 저장 성공으로 표시하지 않는다.
- 스냅샷 저장 실패 시 Spring/DB 보고는 계속 실패로 남긴다. 기존 알림 이벤트를 이미지 없는 텍스트로 큐에 넣은 뒤 저장 예외를 다시 발생시킨다. 잘못된 스냅샷 이름을 DB에 저장하거나 성공으로 가장하지 않는다. 저장 자체가 실패한 경우 callback POST는 보내지 않는다. 기존 이미지 전송 실패의 텍스트 fallback과 같은 알림 내용을 사용한다.
- Discord 오류 로그는 requests 예외 전체 문자열 대신 예외 종류·HTTP 상태만 남긴다. 예외 문자열에 포함될 수 있는 webhook URL 유출을 막는다.

### 기존 이벤트 정책과 분리된 흐름

`SourceWorker._run` → `_run_inference` → `process_detection_events` → 동물/위험 정책 → oracle_service 보고 큐 → 스냅샷·채널/드론 매핑 → Spring POST → `YoloApiReceiverController` → `AlertLinkingService` 트랜잭션 → 탐지/위험 이력과 ALERT_LOG.

Discord는 같은 보고 작업에서 별도 큐로 enqueue하고 단일 notification worker가 webhook으로 전송한다. Spring/Oracle 실패만으로 Discord를 막지는 않는다. Spring ALERT_LOG의 기존 sendStatus 값은 Discord HTTP 전송을 확인한 결과가 아니므로 실제 Discord 성공의 증거로 사용하지 않는다.

- dog/cat 박스가 표시된다는 사실만으로 알림이 생성되지 않는다. 기존 목표 수량 미달 지속 시간·회복 시간·cooldown을 통과해야 한다. 동물 탐지가 전혀 없을 때는 기존 정책대로 미달 타이머를 시작하지 않는다.
- 위험 클래스 blue_alien/blue_shark/pink_dragon/tiger는 기존 소스별·클래스별 cooldown을 따른다. 클래스/도메인 코드/정책은 변경하지 않았다.
- `SSA_OPTIONAL_IO_ENABLED=false`이면 Discord·USB worker를 시작하지 않는다. GPU 자체의 준비 상태와 독립이다. 운영 설정을 자동으로 true로 바꾸지 않았다.

### 재실행 후 읽기 전용 확인

기존 실행 환경변수를 유지한 새 WSL 로그인 세션에서 `id -nG`로 `ssa-upload`의 유효 그룹 반영을 확인한다. 단순히 기존 셸의 `id 사용자명` 출력에 그룹이 나오는 것만으로 해당 셸 권한이 갱신된 것은 아니다. 실제 Flask 실행 계정의 기존 업로드 루트 `test -r`, `test -w`, `test -x`를 확인한다. 기존 사용자 그룹이나 디렉터리 권한을 변경할 필요가 있는지는 이 결과로 판단한다. Tomcat 서비스 sandbox의 쓰기 허용은 별도 계정/namespace에서 확인한다.

```bash
# 기본 로컬 Flask 포트를 사용하는 경우의 읽기 전용 조회
curl --fail --silent http://127.0.0.1:5000/stream/health | python3 -m json.tool
```

health에는 비밀 설정 값을 넣지 않는다. 확인할 필드:

| 필드 | 의미 |
| --- | --- |
| processReady / aiReady / ready / ai.device | 프로세스·실제 AI·전체 초기화 상태와 추론 장치 |
| instanceId / sources.*.frame_sequence | 같은 인스턴스인지와 영상 처리 진행 여부 |
| discord.enabled / configured / workerRunning | optional I/O 허용·webhook 존재·worker 생존 여부 |
| discord.queueDepth / sentCount / failedCount / lastError | 대기·worker 처리 성공/실패와 마지막 안전한 오류 분류 |
| reports.queueDepth / workerRunning / deliveredCount / failedCount / lastError | 보고 큐와 Spring SUCCESS 응답/실패 분류 |

카운터는 해당 프로세스에서 처리한 결과이며 재시작하면 초기화된다. Discord sentCount는 webhook HTTP 요청 성공 수이고, Spring deliveredCount는 SUCCESS 응답 수다. 실제 채널 수신·Oracle 행을 직접 조회한 결과와 동일하다고 단정하지 않는다. 큐에 넣기 전 정책에서 제외되거나 큐가 가득 차 거절된 이벤트는 이 처리 카운터에 포함되지 않는다.

진단 초기 `.env`의 모델·SQLite 경로는 미설정이었다. 이후 사용자가 기존 `project_ssa_yolo/local.sqlite` 사용과 실제 `.env`의 두 경로 변수만 수정하는 예외를 명시적으로 승인했다. `SSA_SQLITE_PATH`와 `SSA_YOLO_MODEL_PATH`만 기존 SQLite/확인된 커스텀 가중치로 설정했고 다른 키·파일 권한·DB 내용은 변경하지 않았다. SQLite는 읽기 전용 quick_check=ok, 테이블 5개를 확인했다. 실제 운영 실행 방식의 `SSA_YOLO_MODEL_PATH`, `SSA_SQLITE_PATH`, `SSA_VIDEO_1_PATH`~`SSA_VIDEO_3_PATH`, 필요 시 `SSA_UPLOAD_ROOT`, `SSA_SPRING_HOST` 및 제어 변수를 기존 값으로 준비해야 한다. 확인되지 않은 모델/SQLite 위치를 새로 만들거나 `.env`를 자동 편집하지 않는다.

### 수정 후 검증과 남은 범위

- 기존 Python 테스트 파일을 확장해 **85 passed**. 실제 외부 요청은 mock했다. 위험 탐지 정책 → 보고 큐 → HTTP 500 mock callback → Discord worker → mock webhook 전달을 확인했다. 동물·위험 모두 스냅샷 실패 시 텍스트 알림 enqueue와 callback 미전송/예외 유지를 확인했다. webhook 오류 문자열 비공개, HTML HTTP 200 거부, optional I/O 비활성화도 확인했다.
- Maven offline verify: **119 tests, 0 failures/errors, 2 skipped** (Windows 전용 및 기본 비활성 GPU 통합 검사). WAR 빌드와 배포 스크립트 `--check`가 통과했고 JDBC 리소스 포함 여부를 값 출력 없이 확인했다.
- 실제 기존 커스텀 가중치 CUDA 추론과 4개 동시 MJPEG test client를 다시 확인했다. 로컬 영상 3개 + 로컬 영상으로 모의한 ESP32, 공유 모델 1개, 모든 MJPEG HTTP 200, health processReady/aiReady/ready 모두 true, device cuda:0, worker 종료 성공. 약 3초 표본 채널당 **14.7~15 FPS**는 Maven 빌드도 진행한 짧은 검사 결과이며 운영 성능 보장이 아니다.
- 기존 Java GPU 통합 검사를 두 번의 시작/종료 사이클로 확장했고 **4 tests, 0 failures/errors**로 통과했다. 실제 `.venv` Flask 시작 → 커스텀 CUDA 워밍업 → health 준비 확인 → 중복 시작 거부 → 토큰 종료를 두 차례 검증했으며 재시작 후 instanceId가 변경됐다. 임시 SQLite/포트/토큰과 비활성 optional I/O를 사용했다. 실제 서비스 계정 권한 검사를 대신하지 않는다.
- 사용자 승인 후 사용자가 관리자 인증으로 기존 배포 스크립트를 실행했다. 백업은 `/var/backups/project-ssa-java17.hkQyGa1D`, Tomcat active/running 및 재시작 시각 2026-10-17 21:20:21 KST를 확인했다. 실제 루트 화면 HTTP 200, metadata API HTTP 200, 재시작 이후 journal 201줄에서 SEVERE/ERROR/Jasper/Oracle 오류가 없었다. 개발 계정은 배포 클래스/JSP 파일의 직접 비교 권한이 없어 해당 바이트 비교는 하지 못했다.
- 배포 후 점검 시점에도 Flask 5000 listener가 없어 사용자가 기존 실행 설정으로 다시 시작하기를 기다리고 있다. 실제 관제 화면의 AI 상태·운영 프로세스 옵션·실제 발생 이벤트의 Oracle 저장·운영 Discord 수신·WSL 외부 네트워크는 아직 미검증이다. Discord 실전송과 운영 데이터 쓰기는 하지 않았으며, 서비스/권한 **설정**도 변경하지 않았다. 실제 ESP32는 별도 작업이다.

### 배포 후 Flask 시작 실패의 확인된 원인

사용자가 보고한 탐지·배터리·센서 세 API의 HTTP 502는 AIStreamBridgeController가 Flask upstream 요청 예외를 잡아 반환하는 응답이다. 배포 후 catalina.out의 최초 Python 예외는 `apps.runtime_settings.RuntimePathError: SSA_SQLITE_PATH must be configured`였다. 대상 저장소의 run_server.py → create_app(local) → LocalConfig.database_uri → readable_file 경로에서 서버 bind 이전에 종료됐다.

사용자가 처음 지정한 별도 `.db` 파일은 0바이트여서 SQLite 헤더가 없었다. 이 파일은 새 DB로 초기화하거나 삭제하지 않았다. 대신 명시적으로 승인받은 기존 local.sqlite를 선택했다. 해당 빈 `.db`는 이미 Git에서 추적 중이고 ignore 대상이 아니다. 운영 DB로 초기화하거나 사용자 데이터를 쓰지 않고 기존 0바이트 상태로 보존했다. 기존 local.sqlite와 .env는 계속 ignored/untracked이며 force add하지 않았다.

기존의 실제 .env 수정 금지 지침에 대해 사용자가 **두 경로 변수에 한정된 예외**를 승인했다. 기존 파일 전체 내용을 출력하지 않고 두 키만 추가했으며 다른 키와 파일 모드의 동일성, SQLite 파일 해시 불변을 확인했다. 개발 계정에서 SQLite/모델 경로 검증이 통과했다. 실제 Tomcat이 시작하는 Flask의 서비스 권한·CUDA·health는 시작 재시도 후 별도로 확인해야 한다.

두 경로 설정 후 시작 재시도의 실제 예외는 `SSA_SQLITE_PATH must reference an existing readable file`로 바뀌었다. 기존 local.sqlite는 개발 계정 소유 0600이고 Tomcat은 tomcat 계정으로 실행된다. 또한 서비스는 ProtectSystem=strict이며 기존 쓰기 예외에 프로젝트 디렉터리가 없다. SQLite는 DB 파일뿐 아니라 저널 생성용 부모 디렉터리 쓰기도 필요하므로 파일 읽기 권한만 풀어서는 충분하지 않다.

`project_ssa_spring/scripts/prepare-flask-sqlite-linux.py`는 기본 읽기 전용이며 기존 DB 무결성·설정 한 키 변경·대상 부재를 검사한다. 명시적인 --apply와 root 인증이 있을 때에만 원본을 보존하는 SQLite backup API 복사, 전용 하위 디렉터리 권한, 한 개 ReadWritePaths drop-in, SSA_SQLITE_PATH 한 키 갱신, Tomcat 재시작을 수행한다. 기존 대상이나 기존 drop-in은 덮어쓰지 않으며 포트 5000에서 Flask가 실행 중이면 적용을 거부한다. 실패 시 생성 파일을 임의 삭제하지 않으므로 검사 후 수동 복구가 필요하다. 비밀 .env 전체를 백업·출력하지 않고 롤백에 필요한 기존 비밀 아닌 SQLite 설정 한 줄만 관리자 전용 백업에 남긴다.

읽기 전용 제안 검증 명령(운영 반영 아님):

```bash
python3 project_ssa_spring/scripts/prepare-flask-sqlite-linux.py --destination /var/lib/project-ssa/flask/local.sqlite
```

전용 경로 복사와 서비스 설정 변경은 별도 사용자 승인 대상으로 제시했으며, 이 사전 검사만으로 적용 완료로 간주하지 않는다.

사용자 승인 후 전용 DB 준비 도중 첫 실행은 복사를 완료한 다음 tomcat 읽기 검사에서 중단됐다. 초기 디렉터리 root:ssa-upload 2770이 실제 runuser tomcat 접근을 허용하지 않았다. 이 시점에는 .env와 service drop-in을 아직 쓰지 않았고 Tomcat 재시작도 하지 않았다. 스크립트는 전용 디렉터리 소유자를 tomcat:ssa-upload로 보완했다. --resume은 원본/복사본의 SQLite 무결성과 스키마·데이터 해시, 디렉터리에 다른 파일이 없는지를 확인하며, 내용이 다르면 중단하고 기존 데이터를 덮어쓰지 않는다. 해당 동작은 임시 DB를 사용하는 기존 test_runtime_paths.py 회귀 검사에 추가했다.

### 승인된 전용 DB 설정 적용 완료

사용자가 --resume --apply를 실행해 동일성 검증된 기존 복사본을 재사용했다. 최종 전용 디렉터리 소유자는 tomcat:ssa-upload 2770, DB는 tomcat:ssa-upload 0660이다. 원본 프로젝트 local.sqlite는 보존됐다. SSA_SQLITE_PATH는 승인된 전용 DB로 변경됐고, `/etc/systemd/system/tomcat10.service.d/ssa-flask-sqlite.conf`에 해당 부모 디렉터리의 ReadWritePaths만 추가됐다. 롤백용 이전 경로 기록은 `/var/backups/project-ssa-sqlite.gxxu6hke`에 남았다. 사용자 완료 출력과 실제 .env 경로·drop-in 내용 일치를 확인했다. 적용 후 실제 Spring 루트 HTTP 200을 확인했고, 이 시점에는 Flask 5000이 꺼져 있어 관리자 화면에서 시작 후 AI/worker 상태를 검증해야 한다.

### 실제 서비스 계정 Flask/AI 시작 확인

전용 DB 적용 후 사용자가 Spring 관리자 버튼으로 시작해 `Flask ON · AI 준비`를 확인했다. 실제 health에서 processReady/aiReady/ready 모두 true, stage AI_READY, device cuda:0을 확인했다. Spring의 `/yolo/detection/status`, `/yolo/battery/status`, `/yolo/envSensor/status` 모두 HTTP 200으로 복구됐다. 따라서 이번 서비스 계정에서는 Flask SQLite 경로/권한 검사를 통과하고 커스텀 모델 CUDA 워밍업도 완료됐다.

Discord는 enabled/configured/workerRunning 모두 true, 큐 0, sentCount/failedCount 모두 0, lastError 없음이었다. Spring 보고 worker도 실행 중이고 처리 카운터는 0이었다. 로그에는 21:38:05 탐지 전체 시작, 21:38:10 탐지 전체 중지 요청이 각각 HTTP 200으로 남았고 이후 영상 3채널은 정지 상태였다. 이 관찰을 실제 알림 전달 성공/실패로 해석하지 않는다. 운영 3채널 자연 탐지에 의한 Oracle 저장과 Discord 실전송 검사는 별도 사용자 승인을 요청했다. ESP32는 해당 검증에서 제외한다.

### 최종 검증 범위 확정

사용자는 운영 3채널 실행에 따른 실제 Oracle 이벤트 저장·Discord 전송 검증을 보류하고 현재 검증으로 마무리하도록 지시했다. 따라서 추가 탐지 시작, 합성 이벤트 POST, 운영 Discord 전송을 하지 않았다. 최종 확인 결과는 실제 Spring 루트 및 세 상태 프록시 HTTP 200, 실제 서비스 계정 Flask/커스텀 CUDA AI 준비 완료, Discord worker 설정·실행 정상이다. 탐지 이벤트→보고→알림은 mock 검사로 검증했고 운영 Oracle 행 저장과 실제 채널 수신은 미검증이다. 현재 영상 3채널 정지 상태를 유지했으며 ESP32 시작 요청도 보내지 않았다. Python 최종 회귀 검사는 85 passed, Maven 검사는 119 tests/실패 0/skip 2, 격리 실제 GPU Flask 수명주기 검사는 4 tests/실패 0(시작·종료 두 사이클)이다.
