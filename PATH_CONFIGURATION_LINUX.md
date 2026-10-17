# Linux 경로 설정 점검 및 운영 준비

후속으로 실제 프로젝트 `.venv`와 GPU 환경을 구축하고 기존 커스텀 모델의 CUDA 추론·Flask 생명주기를 검증했다. 최신 GPU 결과와 실제 운영에서 남은 제한은 [GPU 실행 환경 안내](project_ssa_yolo/GPU_ENVIRONMENT_LINUX.md)를 참고한다. 아래 경로 정리 당시의 격리 테스트 결과와 구분한다.

후속 GPU 점검 시점에는 기존 업로드 디렉터리가 이미 존재했고 로컬 영상 설정도 Linux 경로로 바뀌어 있었다. 이는 이번 GPU 작업 전에 준비된 상태로 보존했다. 아래 초기 조사 당시의 ‘미생성/Windows 경로’ 기록을 현재 상태로 해석하지 않는다.

대상은 현재 저장소이며, 비교한 이전 디렉터리는 같은 workspace의 `ProjectSSASpring-Linux`이다. 비밀 설정의 실제 값, 사용자 데이터, 모델·영상 내용은 이 문서에 기록하지 않는다. 운영 Tomcat, Oracle, ESP32, 외부 API는 이번 점검에서 실행하거나 변경하지 않았다.

## 현재 결정과 설정 우선순위

- Linux 업로드 기본값은 `/var/lib/project-ssa/uploads`, PDF 캐시 기본값은 `/var/cache/project-ssa`다. 각각 `SSA_UPLOAD_ROOT`, `SSA_CACHE_ROOT`로 재정의할 수 있다. 기본값 계산만 하며 운영 디렉터리는 생성하지 않았다.
- 모델·영상·SQLite는 사용자가 **외부 저장소를 별도로 지정**할 예정이다. 파일 이동·DB 초기화·마이그레이션은 하지 않았다. 모델·영상·운영 DB의 암묵적 파일 기본값은 사용하지 않는다. 기존 파일을 환경변수로 명시해야 한다. 테스트는 파일 설정이 없으면 메모리 DB를 사용한다.
- Spring `RuntimeSettings`: 비어 있지 않은 JVM 시스템 속성 → 프로세스 환경변수. Spring은 Flask `.env`를 읽지 않는다.
- Flask: 프로세스 환경변수 → `project_ssa_yolo/.env` → 코드의 기본값. `.env`는 Python 프로젝트 루트에서 읽으며 기존 환경변수를 덮어쓰지 않는다. 설정 모듈 import 전에 로드한다.
- Python의 모델·영상·SQLite 상대경로는 **저장소 루트** 기준으로 해석한다. `REPOSITORY_ROOT`는 파일 위치에서 계산하고 Python 모듈 루트는 그 아래 `project_ssa_yolo`로 계산한다. 공유 업로드 저장소, Spring에서 시작할 Python 실행 파일·Flask 프로젝트 경로, 명시한 PDF 브라우저는 절대경로를 사용한다.
- 설정은 프로세스 시작 시 읽는다. 운영값 적용과 프로세스 재시작은 별도의 운영 작업이다.
- Spring WAR 내부 리소스는 클래스패스와 ServletContext를 사용한다. 배포 서버에 소스 저장소가 있다고 가정해 JSP·Mapper 경로를 호스트 경로로 바꾸지 않는다.

## 권장 기본 디렉터리와 재정의

| 용도 | Linux 기본값 | 재정의 | 파일 생성 여부 |
| --- | --- | --- | --- |
| 원본 사진·탐지 스냅샷 | `/var/lib/project-ssa/uploads` | `SSA_UPLOAD_ROOT` | 설정 로딩·점검 시 생성 안 함 |
| 재생성 가능한 PDF | `/var/cache/project-ssa/pdf-cache/v4` | `SSA_CACHE_ROOT`는 `/pdf-cache/v4` 앞의 캐시 루트 지정 | 설정 로딩·점검 시 생성 안 함 |
| 모델·영상·운영 SQLite | 기본 파일 없음 | 아래 필수 파일 변수 | 파일 생성·이동·자동 다운로드 안 함 |

캐시가 업로드와 분리되므로 과거 PDF의 저장 위치는 변경될 수 있다. 이전 파일이나 DB를 이번 작업에서 수정하지 않았으며, 현재 캐시 루트 밖의 기존 캐시는 실제 PDF 요청 시 재생성 대상이 된다. 기존 위치를 계속 쓰려면 운영자가 검토한 `SSA_CACHE_ROOT`를 명시한다.

## 경로 인벤토리와 실제 소비 위치

| 유형 | 출처와 소비 흐름 | Linux 판단 및 조치 |
| --- | --- | --- |
| 프로젝트 기준 | Python `apps/environment.py`, `runtime_settings.py`; 배포 스크립트의 스크립트 위치 기준 계산 | 셸의 현재 디렉터리와 독립적으로 내부 경로 계산 |
| 업로드·사진·스냅샷 | Spring `RuntimeSettings.uploadRoot()` → `UploadStorage` → 직원·동물·탐지·위험 이미지 처리; Python `oracle_service._save_physical_snapshot()` | 양쪽 `SSA_UPLOAD_ROOT`가 같은 물리 저장소를 가리켜야 함. Linux 기본값 및 명시한 절대경로 사용. Windows 개발 기본값 유지 |
| PDF 저장소 | `PdfCacheServiceImpl.getOrCreatePatrolReportPdf()` → `HeadlessChromePdfRenderer.render()` | `SSA_CACHE_ROOT` 아래 `pdf-cache/v4`. Linux 업로드와 캐시를 분리하고 Windows 미설정 시 업로드 아래 기존 위치 유지. 설정 검증을 요청 시 수행하여 일반 화면 초기화는 유지 |
| PDF 실행 파일 | `HeadlessChromePdfRenderer.resolveBrowserExecutable()` | `SSA_PDF_BROWSER_PATH`를 명시하면 유효한 절대 실행 파일이어야 함. 미설정이면 OS에 맞는 설치 후보/PATH 검색. 명시한 잘못된 설정을 다른 브라우저로 조용히 대체하지 않음 |
| Flask 시작 명령 | `FlaskRuntimeControlService` → `ProcessBuilder` → `run_server.py` | `SSA_FLASK_PROJECT_DIR`, `SSA_FLASK_PYTHON_EXECUTABLE` 검증. 비어 있는 경로를 cwd로 해석하지 않음. 선택 기능이며 실제 프로세스 시작 검증은 미실행 |
| 탐지 모델 | `runtime_settings.YOLO_MODEL_PATH` → `yolo_detector._run_inference()` → Ultralytics | `SSA_YOLO_MODEL_PATH`; 로드 전에 실제 읽을 수 있는 파일인지 확인. 없는 모델명에 대한 자동 다운로드를 방지 |
| 영상 입력 | `VIDEO_PATHS` → `VIDEO_SOURCES` → `SourceWorker._open_capture()` | `SSA_VIDEO_1_PATH`, `SSA_VIDEO_2_PATH`, `SSA_VIDEO_3_PATH`; OpenCV 호출 전 파일 검증. 명시한 Windows 경로를 Linux에서 내부 기본 영상으로 대체하지 않음 |
| Flask SQLite | `apps/config.py` → Flask-SQLAlchemy → `db_test/project_db.py` 및 인증·CRUD | `SSA_SQLITE_PATH` 필수; 실제 파일·접근 권한 검증. 미설정 시 빈 운영 DB를 자동 생성하지 않음. 테스트용 `SSA_TEST_SQLITE_PATH`는 운영 DB와 별도이며 미설정은 메모리 DB |
| 임시 저장소 | Spring `web.xml` multipart, Java `Files.createTempDirectory()` | 컨테이너/JVM 임시 저장소 사용. 업로드 영구 저장소와 다름. Tomcat 서비스는 `PrivateTmp=yes`이므로 다른 프로세스와 `/tmp` 공유를 가정하지 않음 |
| 로그 | Spring `log4j2.xml`의 `logs/app.log`; Python stdout | RollingFile 선언은 cwd 상대이지만 활성 logger는 Console만 참조. 이번 작업에서 파일 로그를 임의 활성화하지 않음 |
| USB 시리얼 | `buzzer_helper.run_mpremote()` 및 `sensor_helper` | `SSA_ESP32_COM_PORT`. Windows COM 기본값은 Windows에서 유지. Linux에는 임의 USB 장치 기본값을 만들지 않으며 장치 경로·접근 권한을 실제 호출 전에 검증 |
| Python / mpremote | `sys.executable -m mpremote` | 실행 중인 Python 환경의 모듈 사용, 셸 PATH의 다른 `mpremote`로 대체하지 않음 |
| Maven / Java / Tomcat | `pom.xml`, `scripts/deploy-tomcat-java17.sh`, `DEPLOYMENT_WSL2.md` | Maven/Java는 실행 환경에서 제공. 배포 스크립트의 Ubuntu Tomcat 인스턴스·백업 위치는 현재 배포 전용이며 범용 경로로 일괄 치환하지 않음 |
| 학습 입력·출력 | `train/train.py::train_yolov12()` | 입력은 프로젝트 기준 기존 파일명 유지 및 사전 검증. 학습 출력은 프로젝트 기준으로 고정. Windows 종료 명령은 Windows에서만 실행. 실제 학습은 미실행 |
| Spring ↔ Flask URL | `AIStreamBridgeController`, `MainController`, `FlaskRuntimeControlService`; Python `oracle_service` | `SSA_FLASK_STREAM_URL`, `SSA_FLASK_ESP32_VIDEO_URL`, `SSA_SPRING_HOST`. HTTP 주소이며 파일 경로가 아님. 배포 context path·포트 일치 확인 필요; 값 변경·접속 미실행 |
| 카메라 및 외부 API | `SSA_ESP32_STREAM_URL`, Oracle JDBC, Discord, Kakao·Open-Meteo·NOAA | 네트워크 설정이며 파일 경로 변경 대상에서 제외. 실제 주소·계정·연결은 검증하지 않음 |
| 웹 라우트·리소스 | `/stream/**`, `/yolo/**`, `/api/v1/ai/**`, `/WEB-INF/views/`, `/resources/**`, `classpath:com/spring/...` | 웹 경로 또는 클래스패스. Linux 호스트 절대경로로 치환하지 않음 |
| ESP32 내부 파일 | Thonny 문서의 `/main.py`, `/boot.py` | MicroPython 장치 파일 시스템이며 호스트 Linux 경로와 다름 |
| vendor 예제 | `yolov5/`, `yolov12/`의 Docker·AWS·학습 예제 | 자체 앱은 설치된 `ultralytics`를 import. vendor 예제 경로를 자체 런타임 설정으로 추정하거나 일괄 변경하지 않음 |

## 복사 파일의 출처·추적 상태

작업 시작 시 기존 변경은 `project_ssa_spring/pom.xml`과 추가 배포 문서·스크립트였다. 이를 보존했다. 두 프로젝트의 비밀·데이터·빌드 ignore 규칙은 동일하며 대상 저장소에는 `Servers/` 중복 규칙이 추가되어 있다. ignore 규칙은 변경하지 않았다.

기존 복사 20개 파일은 원본과 해시가 일치했다. 모두 ignored 상태이다. 계정 설정은 비교 원본과 다르지만 대상의 기존 `jdbc.properties`를 그대로 보존했다.

| 파일 그룹 | 수 | 현재 판단 |
| --- | ---: | --- |
| Flask `.env` | 1 | 원본과 동일. 영상 경로는 Linux에서 유효하지 않은 Windows 형식이며 시리얼 설정도 Windows 형식. 값 수정·출력하지 않음 |
| `local.sqlite` | 1 | Flask 인증·CRUD용 데이터일 수 있음. Oracle과 별도이며 보존. 외부 DB 전환 시 스키마·데이터 이전은 별도 계획 필요 |
| `videos/*.mp4` | 6 | 과거 기본 매핑은 `streaming_0`, `_3`, `_2`였으나 현재는 채널별 환경변수 지정 필수. 복사 파일은 보존하고 실제 사용은 미확정 |
| `.pt` | 11 | 과거 기본 모델은 `runs/detect/my_yolov12_project/yolov8n_train-6/weights/best.pt`였으나 현재는 환경변수 지정 필수. 복사된 모델을 자동 선택하지 않음 |
| ONNX | 1 | 자체 앱에서 직접 로드하는 참조가 발견되지 않음. 삭제하지 않음 |

`project_ssa_yolo/지정된_db_파일명.db`는 기존부터 **tracked**인 0바이트 파일이고 코드 참조가 발견되지 않았다. ignore 규칙이 있어도 기존 추적 파일이 자동 제외되지는 않는다. 삭제·추적 해제하지 않았다.

이전 프로젝트의 `target/`, IDE/Eclipse Servers 설정, 로그, 학습 그래프·CSV·미리보기, 가상환경은 추가 복사하지 않았다. 런타임에 필요한 근거가 없는 파일은 덮어쓰거나 제거하지 않는다.

## 사용자가 지정할 환경변수

실제 값은 문서나 응답에 기록하지 않는다. 아래 변수의 경로가 결정될 때까지 운영 배포와 장비 검증은 보류한다.

| 구분 | 변수 이름 |
| --- | --- |
| 양쪽 프로세스의 공유 저장소 (선택 재정의) | `SSA_UPLOAD_ROOT` |
| Spring PDF 캐시 (선택 재정의) | `SSA_CACHE_ROOT` |
| 외부 모델·영상 | `SSA_YOLO_MODEL_PATH`, `SSA_VIDEO_1_PATH`, `SSA_VIDEO_2_PATH`, `SSA_VIDEO_3_PATH` |
| 외부 Flask DB | `SSA_SQLITE_PATH` |
| 장비별 USB·영상 주소 | `SSA_ESP32_COM_PORT`, `SSA_ESP32_STREAM_URL` |
| 배포 URL 일치 | `SSA_SPRING_HOST`, `SSA_FLASK_STREAM_URL`, `SSA_FLASK_ESP32_VIDEO_URL` |
| PDF 브라우저 | `SSA_PDF_BROWSER_PATH` (미설정 시 설치된 브라우저 검색 가능) |
| 선택적인 Spring의 Flask 시작 기능 | `SSA_FLASK_PROJECT_DIR`, `SSA_FLASK_PYTHON_EXECUTABLE` |
| 격리 테스트 DB | `SSA_TEST_SQLITE_PATH` (운영 DB를 가리키지 않도록 별도 설정) |

Windows용으로 복사된 `.env`의 값은 Linux 셸의 같은 이름 환경변수로 덮어쓸 수 있다. 변수 이름이 같아도 Spring의 JVM 속성이 환경변수보다 우선하므로 두 프로세스의 실제 적용값이 같도록 운영자가 확인해야 한다. 비밀값이나 설정 파일 전체를 출력하는 방식으로 확인하지 않는다.

### 실제 파일 경로를 입력하는 방법

다음은 운영자가 준비한 Python 가상환경의 Bash에서 사용할 안내다. 명령을 이번 작업에서 실행해 운영 설정을 바꾸지는 않았다. 입력할 파일은 이미 존재해야 하며 절대경로를 권장한다. 상대경로는 저장소 루트 기준이다. Windows에서도 같은 변수 이름에 해당 OS의 실제 파일 경로를 명시한다.

```bash
# 선택 재정의. 이 export는 디렉터리 생성이나 systemd 설정 변경을 하지 않는다.
export SSA_UPLOAD_ROOT=/var/lib/project-ssa/uploads
export SSA_CACHE_ROOT=/var/cache/project-ssa

read -r -p '기존 모델 파일 경로: ' SSA_YOLO_MODEL_PATH
read -r -p '기존 video_1 파일 경로: ' SSA_VIDEO_1_PATH
read -r -p '기존 video_2 파일 경로: ' SSA_VIDEO_2_PATH
read -r -p '기존 video_3 파일 경로: ' SSA_VIDEO_3_PATH
read -r -p '기존 SQLite DB 파일 경로: ' SSA_SQLITE_PATH
export SSA_YOLO_MODEL_PATH SSA_VIDEO_1_PATH SSA_VIDEO_2_PATH SSA_VIDEO_3_PATH SSA_SQLITE_PATH
```

공유 저장소 경로만 일치시켜서는 충분하지 않다. Spring에는 Tomcat 실행 환경/JVM 속성으로, Flask에는 Flask 실행 환경으로 전달해야 한다. 실제 `.env`, `jdbc.properties`나 systemd 파일은 자동 편집하지 않는다. 기존 복사 파일을 사용하고 싶다면 위 변수에 명시적으로 지정하되 기존 내용·스키마를 먼저 확인한다.

## 생성 없는 경로·권한 점검

저장소 어디에서 실행하든 아래 도구는 파일 위치에서 저장소 루트를 계산한다. 앱·모델·장치·DB를 실행하지 않고 파일 존재·종류·실행 계정의 읽기/쓰기/디렉터리 검색 권한만 조회한다. 실제 설정값은 출력하지 않는다. 읽기/쓰기 권한 검사는 `access()`이며 파일 생성 방식의 쓰기 시험은 하지 않는다.

```bash
# 저장소 루트에서, Flask 의존성이 있는 가상환경의 Python 사용
python -B project_ssa_yolo/scripts/diagnostics/path_check.py
# 셸의 Spring용 환경변수와 OS 기본값만 점검: Flask .env와 JVM 속성은 읽지 않음
python3 -B project_ssa_yolo/scripts/diagnostics/path_check.py --spring
```

종료 코드 0은 조회한 항목이 모두 준비되었음을, 1은 미설정·누락·권한 문제를 뜻한다. 이 결과는 명령을 실행한 UID 기준이다. 일반 사용자 결과를 Tomcat의 권한 검증으로 간주하지 않는다. 실제 서비스 환경·JVM 속성과 systemd namespace 제한은 별도로 확인해야 한다. 운영자가 승인한 실제 경로에 대해 Tomcat 계정의 `test -r`, `test -w`, `test -x` 검사도 수행할 수 있다. 이 명령들도 디렉터리를 만들지 않는다.

### 이번 읽기 전용 점검 결과

| 항목 | 확인 결과 |
| --- | --- |
| Linux 업로드·캐시 기본 디렉터리 | 둘 다 없음. 생성하지 않음 |
| 기존 상위 `/var/lib`, `/var/cache` | root 소유 0755, 확장 ACL 없음. 개발 계정과 `tomcat`의 POSIX 권한은 읽기·검색 가능, 쓰기 불가 |
| 개발 계정 UID 1000으로 실행한 점검 도구 | 저장소 누락·미설정·잘못된 OS 경로로 종료 코드 1. 코드 실패가 아니라 준비되지 않은 로컬 환경 |
| 모델·SQLite 설정 | 미설정. 복사된 파일을 임의 선택하거나 DB 생성하지 않음 |
| 영상 설정 | 복사된 Windows 경로로 Linux에서 유효하지 않음. 값 출력·수정하지 않음 |
| 홈 디렉터리 경유 저장소 접근 | 홈 디렉터리 0750, 확장 ACL 없음. 현재 `tomcat` 계정의 POSIX 권한에 검색 권한이 없어 로컬 Flask 시작용 경로 접근에 제약 |

Tomcat 계정으로 실제 프로세스를 실행하거나 서비스 환경·권한을 바꾸지는 않았다. 위 POSIX 메타데이터 점검과 실제 운영 namespace 안의 접근 검증은 구분한다. 파일시스템 마운트·ACL·서비스 제한까지 포함한 최종 쓰기 성공은 운영자가 저장소를 준비한 후 확인해야 한다.

## Tomcat·WSL2 운영자가 후속 확인할 항목

- 현재 Ubuntu 패키지 서비스는 `tomcat:tomcat`, `PrivateTmp=yes`, `ProtectSystem=strict`이다. 현재 `ReadWritePaths` 예외는 Tomcat 설정·webapps·로그 위치에 한정된다. 새 공유 업로드/PDF 저장소에 대해 사용자·그룹 권한과 서비스 쓰기 허용 예외를 함께 검토해야 한다. 이번 작업에서는 systemd 설정을 수정하지 않았다.
- 조사한 `/etc/default/tomcat10`에는 `SSA_*` 이름이 없었고 두 Tomcat bin 위치에 `setenv.sh`는 없었다. 일반 셸의 `export`가 이미 실행 중인 systemd 서비스에 반영된다고 가정하면 안 된다.
- 외부 DB는 기존 SQLite 데이터·스키마가 있는 파일이어야 한다. 이 작업은 DB 파일 생성·테이블 생성·마이그레이션을 하지 않는다.
- WSL2의 Windows GPU 전달, USB 연결, 장치 이름·그룹 권한, ESP32-CAM 접근성과 Flask callback 주소는 실제 환경에서 별도 확인한다. 설치되지 않은 브라우저·Python 의존성·장치가 있다고 가정하지 않는다.
- Java 17용 ECJ 조치와 WAR의 로컬 JDBC 포함 검사는 기존 배포 문서를 따른다. 이번 경로 수정은 운영 Tomcat에 반영하지 않았다.

## 남은 별도 확인 후보

- 학습 입력 `yolo12n.pt`, `train/dataset/data.yaml`은 두 프로젝트에 없다. 추론 모델과 학습 시작 가중치는 구분하며 기존 추론 모델을 임의로 학습 입력에 대입하지 않는다.
- `Thonny/normal/start.py`는 보드의 `COMPUTER_IP` 기반 `/api/drone/ready` 호출을 포함하지만 대응 Flask 라우트를 발견하지 못했다. 현재 배포용 `Thonny/main.py`와 구분되는 legacy 후보이며 주소를 임의 변경하지 않았다.
- `Thonny/normal/` 일부 파일에 Wi-Fi 관련 민감 설정 키가 있다. 값은 출력하지 않았고 수정하지 않았다. 별도의 자격 증명 정리가 필요한지 검토해야 한다.

## 실제 수정 파일

| 파일 | 변경 이유 |
| --- | --- |
| `project_ssa_spring/src/main/java/com/spring/util/RuntimeSettings.java` | OS별 업로드·캐시 기본값과 환경변수 재정의, 잘못된 OS 경로 거부 |
| `project_ssa_spring/src/main/java/com/spring/util/UploadStorage.java` | 기본 이미지 동작을 유지하면서 저장소 접근 실패를 로그에 표시 |
| `project_ssa_spring/src/main/java/com/spring/service/PdfCacheServiceImpl.java` | 별도 캐시 루트 사용, 설정 검증을 PDF 요청 시 수행 |
| `project_ssa_spring/src/main/java/com/spring/service/HeadlessChromePdfRenderer.java` | 명시 실행 파일 검증, OS별 브라우저 검색 |
| `project_ssa_spring/src/main/java/com/spring/service/FlaskRuntimeControlService.java` | 프로젝트·진입점·Python 실행 파일 검증, cwd fallback 제거 |
| `project_ssa_yolo/apps/environment.py`, `apps/runtime_settings.py` | 프로젝트 기준 환경 로딩·파일 경로·저장소·장치 검증 통합 |
| `project_ssa_yolo/apps/config.py`, `apps/app.py` | 선택한 SQLite 설정만 검증하고 외부 경로 지원 |
| `project_ssa_yolo/run_server.py`, `apps/services/notifier.py` | 설정 import 전에 프로젝트 `.env` 로딩 |
| `project_ssa_yolo/apps/services/yolo_detector.py` | 모델·영상 사전 검증, 시작 실패를 상태에 반영 |
| `project_ssa_yolo/apps/services/oracle_service.py` | 공통 저장소에서 스냅샷 저장, 실제 저장 실패를 성공 처리하지 않음 |
| `project_ssa_yolo/apps/services/buzzer_helper.py` | 실제 mpremote 호출 전 OS 장치 검증 |
| `project_ssa_yolo/apps/stream/views.py`, `apps/esp32/views.py` | 잘못된 경로로 시작 실패한 legacy 전환 요청에 503/FAIL 반환 |
| `project_ssa_yolo/train/train.py` | cwd 독립 출력, 없는 학습 입력의 사전 오류, Windows 명령의 OS 제한 |
| `project_ssa_yolo/scripts/diagnostics/path_check.py`, `tests/test_path_check.py` | 값 노출·파일 생성 없이 경로와 현재 실행 계정 접근 권한을 점검 |
| `project_ssa_yolo/.env.example` | 필수 모델·영상·SQLite 변수 이름 문서화, 운영 파일 위치를 예시로 추측하지 않음 |
| Spring `RuntimeSettingsTest`, `PdfCacheServiceImplTest`, `HeadlessChromePdfRendererTest`, `FlaskRuntimeControlServiceTest` | 임시 파일·mock 기반 경로 회귀 검사 |
| Python `tests/test_runtime_paths.py`, `test_training_paths.py`, `test_buzzer_helper.py` | 경로·저장 실패·설정 독립성·장치 검증과 기존 lock 회귀 검사 |
| `README.md`, 본 문서, 양쪽 `TESTING.md`, Spring `UPLOAD_STORAGE.md`, `DEPLOYMENT_WSL2.md` | 실제 설정 계약, 운영 미반영 상태, 테스트 결과 기록 |

기존 `pom.xml` 변경과 배포 스크립트는 이번에 수정하지 않았다. `.gitignore`, 비밀 설정, 복사된 데이터 파일도 변경하지 않았다.

## 경로 정리 당시 검증 결과

- Java 17, Maven 오프라인 `mvn -o verify`: **BUILD SUCCESS**, 115개 중 실패·오류 0, Windows 전용 1개 skip. 초기 샌드박스의 Mockito JVM attach 제한은 승인된 샌드박스 외부 실행에서 해소됐다.
- Python 3.11 집중 경로·학습·부저 검사: **41 passed**. 전체 자체 테스트는 추가 격리 harness에서 **68 passed**.
- 전체 Python 테스트는 실제 네트워크·서브프로세스·DB 연결·카메라 입력을 차단하고, Ultralytics 생성 시 실패하는 테스트 전용 import stub을 사용했다. 실제 PyTorch/Ultralytics/CUDA 설치·추론 성공을 검증한 결과는 아니다.
- 자체 Python 44개 문법 검사, 배포 스크립트 `bash -n`, `git diff --check` 통과.
- 보호 대상 로컬 파일 21개(기존 복사 20개 및 대상 JDBC)의 내용·크기·권한이 작업 시작과 일치했다. 민감 파일은 ignored/untracked이며 staging/commit을 하지 않았다.

검증 방법은 각 모듈 `TESTING.md`를 참고한다. 운영 파일 권한·외부 DB 데이터·실제 장비·Windows 실행·운영 Tomcat 반영은 별도 검증 대상이다.
