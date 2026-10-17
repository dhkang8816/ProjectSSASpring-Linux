# WSL2 운영 권한 및 SQLite 분리 기록

2026-10-17 사용자 승인 후 적용했다. 대상은 `ProjectSSASpring-Linux-git`, 서비스는 `tomcat10.service`, 실행 계정은 `tomcat:tomcat`, 공유 그룹은 `ssa-upload`다. 실제 비밀 설정 값은 기록하지 않는다. 이전 경로/GPU 문서의 미반영·SQLite 필수 기록보다 이 문서가 최신이다.

## 원인과 적용 결과

| 검사 대상 | 기존 문제 | 수정 사항 | 검증 결과 |
| --- | --- | --- | --- |
| 업로드 루트 | 일반 계정 검사에서는 쓰기 가능했지만 `ProtectSystem=strict`의 서비스 namespace에서는 쓰기 불가 | 해당 루트만 systemd 쓰기 예외 추가, 기존 소유권 유지 | 호스트/서비스 namespace에서 생성·읽기·삭제 통과 |
| 업로드 하위 저장소 | 코드가 쓰는 네 디렉터리 없음 | `member`, `animals`, `detection`, `dangerlog`에 전용 그룹·setgid·기본 ACL | 각 폴더 임시 파일 0660 및 `ssa-upload` 확인 |
| Java multipart 파일 | spool 파일 rename 시 디렉터리의 setgid/기본 ACL만으로 최종 권한을 보장하지 못함 | 새 파일에 디렉터리 그룹과 POSIX 0660 적용 | 배포된 helper로 임시 PNG 저장·재조회·삭제 통과 |
| PDF/AI 캐시 | 캐시 디렉터리 없음, 서비스 쓰기 예외 없음 | 알려진 캐시 경로만 준비, 쓰기 예외 및 Ultralytics 설정 경로 지정 | PDF 캐시/AI 설정 디렉터리 쓰기 통과; 실제 PDF 렌더링은 미검증 |
| 소스·venv·인터프리터·모델·영상 | 과거 홈 접근 문제는 이미 제한된 ACL로 해결된 상태 | 불필요한 권한 변경 없음 | 두 검사 환경에서 24,545개 소스/venv 파일 읽기 거부 0건, 모델·영상 읽기 성공 |
| `.env` / 서비스 환경 파일 | 비밀 파일은 일반 소스와 구분해야 함 | 기존 보호 권한 유지 | `.env`의 Tomcat 전용 읽기 ACL 유지, 서비스 환경 파일은 root 0600 유지 |
| SQLite | 모든 Flask 시작이 기존 DB 화면 초기화까지 수행 | 기본 AI 모드에서 DB 엔진·모델·기존 화면 초기화 분리 | SQLite 설정 없는 시작·CUDA 추론·스트리밍·Spring 제어 통과 |
| Oracle | 파일 권한과 DB 연결 문제 구분 필요 | 연결 설정/데이터 변경 없음 | 실제 서비스 계정과 namespace의 읽기 전용 SELECT 통과 |
| DB 이미지 참조 | 회원·동물 사진 참조 각 1건에 대응 파일 없음 | 자동 대체·복사·DB 수정 없음 | 후속 복구 필요, 아래 제한 참고 |

## 실제 디렉터리와 최소 권한

- `/var/lib/project-ssa/uploads`: 기존 `root:ssa-upload` 소유권 유지, 2770, Tomcat/공유 그룹의 읽기·쓰기·검색 ACL. 파일은 이동하거나 삭제하지 않았다.
- 위 루트의 `member`, `animals`, `detection`, `dangerlog`: `tomcat:ssa-upload`, 2770. 기본 ACL은 소유자·Tomcat·공유 그룹에 rwx, 기타 사용자에는 권한을 주지 않는다. 일반 파일 생성 시 실행 비트는 생기지 않는다.
- `/var/cache/project-ssa`, `pdf-cache`, `pdf-cache/v4`, `ai`, `ai/Ultralytics`: `tomcat:ssa-upload`, 2770 및 같은 공유 ACL. 코드가 사용하는 경로만 준비했다.
- 서비스 `UMask=0007`: 일반 신규 파일 0660. 실제 파일 생성 검사에서 공유 저장소의 그룹은 `ssa-upload`였다. Java 업로드는 spool rename도 처리하도록 새 파일의 그룹·0660을 명시한다. Windows는 POSIX 파일 속성이 없으면 기존 처리를 유지한다.
- 개발자 홈은 기존 0750 및 Tomcat 전용 검색(`--x`) ACL을 유지했다. 홈 목록 공개나 전체 소스의 재귀 chown/chmod를 하지 않았다.
- 실제 Flask `.env`는 기존 0640 및 Tomcat 전용 읽기 ACL을 유지했다. `/etc/project-ssa/tomcat.env`는 root:root 0600이다. 후자는 systemd가 읽어 프로세스에 전달하므로 Tomcat의 직접 읽기 권한이 필요하지 않다.
- 서비스의 private 임시 공간 및 기존 Tomcat 로그 경로도 임시 파일 쓰기·읽기·삭제가 성공했다. 로그 디렉터리의 기존 그룹은 바꾸지 않았다.
- 드론 이미지는 현재 정적 리소스이며 별도 업로드 API/저장 컬럼을 확인하지 못했다. 임의의 `uploads/drone` 경로를 만들지 않았다.

## systemd 적용 내용

추가한 파일은 `/etc/systemd/system/tomcat10.service.d/ssa-runtime-permissions.conf`다.

```ini
[Service]
SupplementaryGroups=ssa-upload
UMask=0007
ReadWritePaths=/var/lib/project-ssa/uploads /var/cache/project-ssa
Environment=SSA_FLASK_PROFILE=ai
Environment=SSA_CACHE_ROOT=/var/cache/project-ssa
Environment=YOLO_CONFIG_DIR=/var/cache/project-ssa/ai
```

기존 `ProtectSystem=strict`, `PrivateTmp=yes`, `NoNewPrivileges=yes` 및 Tomcat의 기존 쓰기 예외는 유지했다. `ProtectHome=no`는 기존 값이다. 광범위한 홈 쓰기 예외는 추가하지 않았다. 기존 WorkingDirectory/ReadOnlyPaths/InaccessiblePaths/EnvironmentFiles 값은 진단 JSON에 기록했고 임의 변경하지 않았다. Spring이 생성하는 Flask 자식은 이 서비스의 계정·보조 그룹·umask·namespace·환경을 상속한다.

AI 모드는 SQLite에 쓰지 않으므로 기존 `ssa-flask-sqlite.conf`를 `.conf.disabled`로 보존하고 `/var/lib/project-ssa/flask` 쓰기 예외를 비활성화했다. SQLite 파일과 디렉터리의 데이터·권한은 변경하지 않았다. 기존 화면을 다시 서비스에서 제공하려면 `local` 모드와 DB 경로/전용 쓰기 예외를 별도로 검토해야 한다.

프로세스 환경은 Flask `.env`보다 우선한다. Spring 경로 설정은 JVM `-D` 속성이 환경변수보다 우선한다. 실제 `.env`, JDBC 파일, `/etc/project-ssa/tomcat.env` 값은 이번 작업에서 편집하지 않았다. 서로 다른 설정을 추가할 때는 실제 서비스 프로세스 기준으로 다시 점검해야 한다.

권한/서비스 설정 백업은 `/var/backups/project-ssa-permissions._g5o21et`, 기존 WAR 백업은 `/var/backups/project-ssa-java17.hzz9fkkX`다. 권한 백업에는 기존 ACL·drop-in·새로 만든 디렉터리 목록이 있다. 원복이 필요하면 백업과 현재 상태를 먼저 비교해야 하며 운영 디렉터리를 일괄 삭제하지 않는다.

## SQLite 실제 호출 경로와 분류

`apps/db_test`는 이름과 달리 테스트 전용 모듈이 아니다. 기존 Flask 화면의 실제 모델을 정의한다. 이전 `run_server.py → create_app("local") → LocalConfig.database_uri() → db.init_app()/Migrate → project_db 및 기존 blueprint 등록`이 운영 AI에도 SQLite를 요구한 원인이다.

| 구분 | 실제 파일·호출 | 처리 |
| --- | --- | --- |
| 현재 Spring 관제의 운영 기능 | `yolo_detector.SourceWorker` → `process_detection_events()` → `oracle_service`의 report queue/HTTP → Spring `YoloApiReceiverController` → `AlertLinkingService` 및 MyBatis → Oracle | SQLite 호출 없음. 영상·탐지 클래스·이벤트 정책·Oracle payload 유지 |
| 기존 Flask 사용자 화면 | `auth/views.py`의 `signup()/login()`, `crud/views.py`의 사용자 등록·목록·승인·수정·삭제 → `User.query`, `db.session` | 실제 구현이 있으므로 삭제하지 않고 `local` 모드로 보존 |
| 기존 Flask 기록·설정 화면 | `detect_data/views.py`의 `animal_db()/update_animals()/danger_db()/detect_animal()` 및 삭제·내보내기, `control_page/views.py`의 로그인 보호 화면 → `Animals`, `Detect_animal`, `Dangers` | 운영 사용 여부를 단정하지 않음. 확보한 요청 로그에는 해당 화면 호출이 없었으며 사용자 승인으로 모드 분리 |
| 로컬 모델·인증 상태 | `db_test/project_db.py`의 위 네 모델 및 `User.load_user()` → Flask-Login 세션 사용자 조회 | `local`/`testing`에서만 모델 import 및 DB 초기화 |
| 테스트 | `TestingConfig.database_uri()` → 기본 메모리 SQLite, 또는 별도 `SSA_TEST_SQLITE_PATH` | 운영 DB를 테스트 대상으로 사용하지 않음 |
| 마이그레이션·DB 도구 | `migrations/`, `apps/extensions.py`, `prepare-flask-sqlite-linux.py` | 기존 UI/관리 도구로 보존. AI 시작에서는 실행하지 않음 |
| AI에서 불필요한 의존성 | Flask-SQLAlchemy/Flask-Migrate 및 기존 화면의 pandas/email-validator | AI 앱 초기화 경로에서 제외. `requirements-ai.txt`에서 제외하되 설치된 패키지나 전체 requirements는 삭제하지 않음 |

AI 기본 모드는 `ai`이고 `/stream`, `/esp32_yolov12` 영상·제어 API를 유지한다. `/`는 AI 프로필/health 위치를 JSON으로 반환하며 기존 DB 화면은 등록하지 않는다. health 조회만으로 모델을 로드하거나 장치/Discord worker를 시작하지 않는다. 모델 준비는 기존 보호된 초기화 API와 실제 CUDA 워밍업 결과로 판단한다.

명시적으로 기존 UI를 실행하려면 Linux에서는 `export SSA_FLASK_PROFILE=local`, PowerShell에서는 `$env:SSA_FLASK_PROFILE='local'`을 설정한다. 이후 해당 OS의 기존 DB 파일을 `SSA_SQLITE_PATH`로 지정하고 원래 `run_server.py`로 실행한다. 파일과 부모의 읽기/쓰기·검색 권한이 필요하다. DB 파일을 자동 생성하거나 데이터를 이전하지 않는다. Flask CLI의 factory 인자도 `create_app("local")`로 명시해야 하며 `FLASK_APP`과 `SSA_FLASK_PROFILE`이 서로 다른 모드를 지시하지 않도록 한다.

기존 `project_ssa_yolo/local.sqlite` 원본과 이전에 승인해 복사한 `/var/lib/project-ssa/flask/local.sqlite`는 보존했다. WAL/SHM 파일 생성이나 운영 SQLite 읽기/쓰기를 회귀 검사에 요구하지 않는다. 현재 AI 모드는 DB 엔진이 없으므로 SQLite 권한이 AI 가동의 전제 조건이 아니다.

## 재발 방지 진단 도구

`project_ssa_spring/scripts/linux-runtime-permissions.py`는 기본 읽기 전용이다. 실제 PID의 uid/gid/보조 그룹·환경·cwd·umask를 확인하고, 별도 검사 프로세스가 해당 계정으로 권한을 낮춰 호스트 및 실제 Tomcat mount namespace에서 접근을 비교한다. 부모 경로와 주요 대상의 소유권·모드·ACL을 수집하고 `--full`은 소스/venv를 내용 열람 없이 순회한다. 전체 cgroup/보안 속성까지 새 프로세스에 복제하는 것은 아니므로 실제 Spring 버튼의 자식 실행 결과와 구분한다.

저장소 루트에서 읽기 전용 검사:

```bash
sudo project_ssa_yolo/.venv/bin/python -B \
  project_ssa_spring/scripts/linux-runtime-permissions.py --full
```

JSON 저장은 `--report`로 새 파일명을 지정한다. 기존 보고서는 덮어쓰지 않는다. 실제 설정/토큰/비밀번호는 출력하지 않지만 파일 경로와 권한 정보가 포함되므로 보고서를 공개 저장소에 올리지 않는다.

선택 옵션은 다음과 같다.

| 옵션 | 범위 |
| --- | --- |
| `--verify` | 기존 런타임 디렉터리에 고유 임시 파일 생성·재조회·삭제, 배포된 Java 이미지 저장/읽기 helper 검사. 기존 사용자 파일은 수정하지 않음 |
| `--oracle` | 배포된 JDBC 설정으로 `SET TRANSACTION READ ONLY`, `SELECT 1 FROM DUAL`, 네 테이블의 이미지 참조 집계. 실제 행 값/파일명은 출력하지 않고 DML 없음 |
| `--gpu` | 사용자 확인 가중치의 SHA-256 검증 후 CUDA 초기화·기존 세 영상 첫 프레임 추론/JPEG. 외부 socket/subprocess와 이벤트 전송 차단 |
| `--apply` | root 승인 후 검토된 두 루트에만 ACL/디렉터리·전용 drop-in 적용, 기존 Flask 정상 종료 및 Tomcat 재시작. 기본 진단과 명시적으로 분리 |
| `--deploy-war` | `--apply`와 함께만 사용. 기존 배포 스크립트로 백업 후 WAR 교체, HTTP 준비 및 업로드 helper 클래스 일치 확인 |

적용 모드는 현재 검토한 업로드/캐시 루트 외의 경로, 예상과 다른 기존 그룹/drop-in, 심볼릭 링크를 만나면 임의 변경을 거부한다. 권한 상승은 sudo 인증을 우회하지 않는다. 반복 점검에는 읽기 전용 모드를 사용하고 재적용은 변경 계획을 검토한 후 수행한다.

## 검증 근거와 남은 범위

- 적용 전/후 보고서: `/tmp/ssa-permission-audit-before.json`, `/tmp/ssa-permission-audit-after.json`. 적용 후 양 환경에서 경로 오류 0건, 필수 설정 누락 0건, Spring/Flask 업로드 루트 일치.
- 실제 서비스 계정/namespace의 Oracle 읽기 전용 SELECT와 참조 집계 통과. 회원 2행 중 기본 이미지 1건·파일 없는 참조 1건, 동물 6행 중 기본 이미지 5건·파일 없는 참조 1건이다. 탐지/위험 로그는 각각 0행이다. 저장소 순회에서도 기존 파일 0개여서 두 참조는 ACL 차단과 구분되는 파일 부재다. 원본 사진을 확인한 뒤 별도 복구가 필요하다.
- 배포된 Java helper의 임시 이미지 저장·재조회·0660/그룹 확인 및 검사 파일 삭제 통과. 실제 회원 화면 인증·HTTP multipart·회원 DB 갱신까지 수행한 검사는 아니다.
- 실제 서비스 namespace에서 RTX 3080 / `cuda:0` 인식, 모델 준비 성공, SQLite 엔진 없음. 현재 설정의 세 영상 첫 프레임 디코딩/JPEG/추론 통과(탐지 수 2/3/3). Python/CUDA/Ultralytics/모델 버전은 변경하지 않았다.
- Python 전체 **88 passed**. 이후 기존 테스트를 보강해 로컬 화면의 메모리 DB 읽기·쓰기와 진단 임시 파일 이름 충돌 시 기존 파일 보존까지 검사한 관련 테스트 **37 passed**. Maven `mvn -o verify`: **120 tests, 0 failures/errors, 2 skips**. 별도 실제 Java 서비스 제어 격리 검사 **4 passed**, SQLite 없이 Flask 시작·중복 실행 차단·정상 종료를 두 사이클 확인.
- 별도 GPU 회귀 검사는 단일 공유 모델·네 동시 MJPEG 연결을 통과했다. 영상 3개와 로컬 영상으로 모의한 ESP32이며 실제 장비/Discord/Oracle 이벤트는 차단했다.
- 사용자가 실제 Spring 관리자 화면의 시작 → AI 준비 → 종료/OFF → 재시작/AI 준비를 확인했다. 적용 스크립트의 Spring HTTP 준비 검사도 통과했다. 이후 별도 직접 health HTTP 재조회는 실행 권한이 허용되지 않아 수행하지 못했으므로 이 부분은 사용자 화면 확인과 서비스 계정 GPU 검사 근거를 구분한다.
- PDF 캐시 접근은 정상이나 실행 가능한 Chrome/Chromium/Edge 또는 지정 브라우저는 확인되지 않았다. 브라우저 설치/경로 지정 후 실제 보고서 렌더링 검사가 필요하다. 이번에 브라우저나 OS 패키지를 설치하지 않았다.
- 실제 ESP32/USB 부저·센서, 실제 Oracle 탐지 INSERT, Discord 실전송, 운영 3채널 재가동 및 장시간 지연/VRAM 검사는 하지 않았다. 사용자 보류 지침을 유지했다.

현재 기본 AI 모드를 막는 확인된 권한 오류나 미완료 관리자 적용은 없다. 누락된 두 사진과 PDF 브라우저 등 위 후속 항목은 별도다. 실제 `.env`/JDBC 파일은 ignored 상태를 유지하고 커밋하지 않았다.
