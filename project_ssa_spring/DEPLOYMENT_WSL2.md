# WSL2 · Tomcat 10 · Java 17 배포 메모

최신 상태: 사용자 승인으로 권한 정상화·WAR 배포·Tomcat 재시작을 완료했다. 업로드·캐시 쓰기 및 실제 서비스 계정 CUDA/Oracle SELECT 검사를 통과했고 기본 Flask는 SQLite 없는 `ai` 모드다. [운영 권한 안내](../LINUX_RUNTIME_PERMISSIONS.md)에 실제 drop-in·백업·검증 범위가 있다. 아래 과거 미반영·SQLite 조치 기록과 구분한다.

## 이전 GPU 실행 제어 변경 기록

Flask 프로세스 응답(`processReady`)과 커스텀 YOLO CUDA 추론 준비(`aiReady`)를 구분한다.
현재 `FlaskRuntimeControlService`는 토큰으로 보호된 Flask startup-status를 확인하며,
JSP 버튼도 AI 미준비/준비를 별도 표시한다. HTTP 200만으로 AI 준비를 선언하지 않는다.

개발 계정에서 실제 `.venv` Flask 실행 → CUDA 연산/커스텀 모델 추론 → 중복 시작 차단 → 정상
종료를 검증했다. 운영 Tomcat 재배포·재시작은 하지 않았다. `tomcat`의 개발자 홈 검색 권한,
홈 아래 Python 인터프리터 접근, 서비스의 쓰기 제한과 실제 GPU 접근은 승인 후 별도 검증해야 한다.
설치 명령·고정 버전·실제 결과·격리 재검증 도구는 [GPU 안내](../project_ssa_yolo/GPU_ENVIRONMENT_LINUX.md)에 있다.

## 후속 경로 설정 변경 (未배포)

전체 [경로 점검](../PATH_CONFIGURATION_LINUX.md) 이후 코드는 Linux의
업로드 기본값은 `/var/lib/project-ssa/uploads`, PDF 캐시 기본값은 `/var/cache/project-ssa`다.
`SSA_UPLOAD_ROOT`, `SSA_CACHE_ROOT`로 각각 재정의할 수 있다. 두 디렉터리는 준비하지 않았으므로
아래 과거 배포 결과를 새 경로의 운영 검증 결과로 해석하지 않는다. PDF는 캐시 루트의
`pdf-cache/v4`를 사용하며 경로 검증은 파일/PDF 요청 시 수행한다. `.env`나 JDBC 파일은 변경하지 않았다.

외부 모델·영상은 Flask 실행 환경에서 별도로 지정한다. SQLite는 명시적 `local` 모드에서만 필요하다. Spring이 Flask를 시작하는
선택 기능에는 `SSA_FLASK_PROJECT_DIR`, `SSA_FLASK_PYTHON_EXECUTABLE`의 유효한 절대경로가
필요하다. PDF는 `SSA_PDF_BROWSER_PATH` 또는 실행 가능한 설치 브라우저가 필요하다.
실제 파일 경로와 설치 여부를 확인하지 않은 채 예시를 운영값으로 사용하지 않는다.

현재 Ubuntu 패키지 Tomcat은 `PrivateTmp=yes`, `ProtectSystem=strict`이며 쓰기 허용
예외가 제한되어 있다. 외부 업로드/PDF 저장소는 공유 그룹·권한과 systemd `ReadWritePaths`
예외를 함께 검토한다. 일반 셸의 `export`는 실행 중인 systemd 서비스에 자동 적용되지 않는다.
이번 작업은 운영 파일 변경, 서비스 재시작, DB/장비/API 요청을 수행하지 않았다.

## 확인한 HTTP 500 원인

2026-10-17 Tomcat `localhost` 로그에서 Spring 초기화 후 JSP 처리 중 다음 오류가 발생했다.

```text
UnsupportedClassVersionError: org/eclipse/jdt/internal/compiler/env/INameEnvironment
class file version 65.0; runtime only recognizes class file versions up to 61.0
```

Java 17은 class version 61까지 지원한다. Ubuntu 패키지의
`/usr/share/java/eclipse-jdt-core-compiler-batch-3.35.0.jar`에 들어 있는 해당 클래스는
version 65(Java 21)이다. Tomcat의 `tomcat10-jasper-10.1.55.jar` Manifest는
`eclipse-jdt-core.jar`와 `eclipse-jdt-core-compiler-batch.jar`를 `Class-Path`로 참조한다.
Jasper가 컴파일러를 만드는 단계에서 실패하므로 현재 오류의 직접 원인은 이 조합이다.

프로젝트의 Servlet 6.0 / JSP 3.1 API는 `provided`이고 JSTL은 Jakarta 3.x이다.
`MainController.main()` → `main` → `/WEB-INF/views/main.jsp`의 ViewResolver 연결도 확인했다.
WAR의 `WEB-INF/lib`에 ECJ를 추가하는 것만으로는 Tomcat 부모 로더의 컴파일러를 교체할 수 없다.

## WAR 재빌드와 JDBC 설정

아래 명령은 `project_ssa_spring` 디렉터리에서 실행한다. 실제 JDBC 설정은 로컬 파일
`src/main/resources/com/spring/properties/jdbc.properties`에 두며, 저장소의 `.gitignore`가
이를 제외한다. 계정 정보와 비밀번호를 문서·로그·커밋에 넣지 않는다. URL·계정 값을 출력하는
명령도 사용하지 않는다. Oracle 및 Windows 네트워크·방화벽 설정은 변경하지 않는다.

```bash
test -s src/main/resources/com/spring/properties/jdbc.properties
mvn clean verify
```

`pom.xml`의 `require-local-jdbc-settings` 실행은 `prepare-package` 단계에서 원본과
`target/classes`의 실제 설정 파일 존재 여부를 검사한다. 누락 상태로 WAR를 만들면
빌드가 실패하며, `mvn test`만 실행할 때는 로컬 DB 설정을 요구하지 않는다.

기본 Maven resources 복사로 실제 파일이 WAR의
`WEB-INF/classes/com/spring/properties/jdbc.properties`에 포함되어야 한다.
파일명에 `.example`을 붙인 파일만 배포해서는 안 된다. 이전 WAR에는 수동 추가된
최상위 `com/spring/properties/jdbc.properties`도 있었으므로 기존 산출물을 재사용하지 않는다.
`clean`은 프로젝트 `target`을 정리하며 시스템 파일을 삭제하지 않는다.

다음 검사는 JDBC 내용 없이 배치 위치만 검사한다.

```bash
python3 - <<'PY'
from zipfile import ZipFile

with ZipFile('target/project_ssa_spring-0.0.1-SNAPSHOT.war') as war:
    entries = [name for name in war.namelist() if name.endswith('/jdbc.properties')]
    assert entries == ['WEB-INF/classes/com/spring/properties/jdbc.properties'], entries
print('JDBC resource placement: OK')
PY
```

WAR 자체에도 자격 증명이 포함되므로 배포 담당자만 접근할 수 있게 보관하고 공개 업로드하지 않는다.

## Java 17을 유지하는 Tomcat 수정안

2026-10-17 운영 반영 및 HTTP 검증을 완료했다. 다음은 같은 구성을 재현하는 절차이며,
재적용할 때도 관리자가 검토한 후 수행한다.
Ubuntu의 시스템 JAR를 삭제하거나 덮어쓰지 않고, upstream ECJ를 Tomcat 인스턴스의
`lib`에 추가한다. 먼저 해당 인스턴스의 `conf/catalina.properties`에서
`common.loader`가 `${catalina.base}/lib/*.jar`를 `${catalina.home}/lib/*.jar`보다 먼저
읽는지 확인한다. 순서가 다르면 이 절차를 그대로 적용하지 않는다.

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy \
  -Dartifact=org.eclipse.jdt:ecj:3.35.0 \
  -DoutputDirectory=target/tomcat-java17

javap -verbose -classpath target/tomcat-java17/ecj-3.35.0.jar \
  org.eclipse.jdt.internal.compiler.env.INameEnvironment
```

upstream JAR가 Java 17에서 로드 가능하고 class version이 61 이하인지 확인한다.
동일한 3.35.0 버전명이어도 Ubuntu가 빌드한 JAR와 upstream JAR의 실행 Java 요구사항은
다를 수 있다. 운영 반영 전에 별도 Tomcat 인스턴스에서 JSP 렌더링까지 확인한다.

아래 `sudo` 작업에는 관리자 승인과 대화형 비밀번호 입력이 필요할 수 있다.
대상 파일이 이미 있으면 먼저 날짜가 붙은 백업을 만든다. 다른 ECJ JAR가 인스턴스의
`lib`에 존재한다면 중복 로딩을 먼저 검토하며 임의로 삭제하지 않는다.

```bash
if [ -e /var/lib/tomcat10/lib/ecj-3.35.0.jar ]; then
  sudo cp -a /var/lib/tomcat10/lib/ecj-3.35.0.jar \
    "/var/lib/tomcat10/lib/ecj-3.35.0.jar.backup-$(date +%Y%m%d-%H%M%S)"
fi
sudo install -m 0644 target/tomcat-java17/ecj-3.35.0.jar \
  /var/lib/tomcat10/lib/ecj-3.35.0.jar
```

재빌드한 WAR를 기존 배포 절차로 반영한 후, 관리자의 확인을 받아 재시작한다.

```bash
sudo systemctl restart tomcat10
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' \
  http://localhost:8080/project_ssa_spring-0.0.1-SNAPSHOT/
```

재시작 전후 로그 구간을 구분해 새 `UnsupportedClassVersionError`가 없는지 확인하고,
루트 화면뿐 아니라 로그인·공통 include를 사용하는 JSP도 검증한다.
운영 반영 및 검증 결과는 실제 수행한 결과에 맞춰 별도로 기록한다.

## 준비된 적용 스크립트

위 수동 절차 대신 준비된 스크립트로 같은 변경을 적용할 수 있다. 먼저 `mvn clean verify`와
ECJ 다운로드를 순서대로 끝낸다(`clean`은 `target/tomcat-java17`도 지운다).

```bash
bash scripts/deploy-tomcat-java17.sh --check
# 관리자 검토·승인 후 운영 터미널에서 실행한다. 잠시 서비스가 중단된다.
sudo bash scripts/deploy-tomcat-java17.sh --apply
```

`--check`는 파일·서비스를 변경하지 않는다. `--apply`는 실제 `common.loader` 순서를
검사하고 다른 ECJ/JDT JAR가 있으면 중단한다. 기존 WAR·전개 디렉터리·기존 ECJ를
접근 제한된 `/var/backups/project-ssa-java17.*`에 백업한 뒤, 인스턴스 ECJ와 WAR만
설치하고 Tomcat을 재시작한다. Ubuntu 시스템 JAR·Windows·DB 설정을 수정하지 않는다.
전개 디렉터리를 스크립트가 삭제하지 않으며 새 WAR 전개는 Tomcat이 처리한다.

## 이번 검증 결과

- Java 17에서 `mvn clean verify`: 102개 테스트, 실패·오류 0, BUILD SUCCESS.
- 새 WAR의 실제 JDBC 파일은 `WEB-INF/classes`에만 있고 로컬 원본과 바이트가 일치한다.
- WAR에 Servlet/JSP API, Jasper, ECJ가 포함되지 않음을 확인했다.
- upstream ECJ 3.35.0의 일반 클래스 전체가 major 61 이하임을 확인했다.
- `/tmp`의 별도 CATALINA_BASE, 동일 Ubuntu Tomcat 10.1.55, Java 17, upstream ECJ로
  실제 WAR를 실행했다. 포트는 `127.0.0.1:18080`이며 운영 8080은 변경하지 않았다.
- 루트·로그인·채널 상세 JSP 및 읽기 전용 AI targets API가 HTTP 200을 반환했다.
- 사용자가 관리자 터미널에서 적용 스크립트를 실행했다. 기존 배포 백업은
  `/var/backups/project-ssa-java17.L7cFg3vq`에 보관된다.
- 운영 Tomcat은 2026-10-17 18:00 KST에 재시작되었고 `active/running`을 확인했다.
  Java 17을 유지하며 인스턴스의 ECJ 클래스 버전은 61이다.
- 운영 포트 8080에서 `/`, `/login`, `/yolo/detail?channel=video_1`,
  `/api/v1/ai/targets` GET이 모두 HTTP 200을 반환했다.
- 새 배포 이후 localhost/catalina 로그에 `UnsupportedClassVersionError`가 없음을 확인했다.
  `WEB-INF`의 JDBC 직접 요청은 404였으며 WAR의 공개 경로에는 JDBC 파일이 없다.
- DB 계정·접속 URL·Windows 네트워크·방화벽은 이번 수정에서 변경하지 않았다.


## Flask SQLite 서비스 경로 적용 기록

아래는 AI 모드 분리 이전의 조치다. 현재 DB 파일은 보존하고 SQLite 쓰기 drop-in은 `.conf.disabled`로 비활성화했다. AI 서버는 이 DB에 의존하지 않는다.

Flask가 `SSA_SQLITE_PATH must be configured`로 종료되고 이후 개발 계정 소유 DB의 읽기 권한 검사에서도 종료된 문제가 있었다. 사용자 승인으로 기존 `project_ssa_yolo/local.sqlite` 원본을 보존하고 `/var/lib/project-ssa/flask/local.sqlite`로 SQLite backup API 복사를 적용했다. 실제 `.env`에서 SQLite/모델 경로 두 키만 설정하는 예외와 이후 SQLite 전용 경로 갱신을 각각 승인받았다. 토큰·webhook·JDBC 값은 변경하지 않았다.

`/etc/systemd/system/tomcat10.service.d/ssa-flask-sqlite.conf`는 새 SQLite 부모 디렉터리의 ReadWritePaths만 추가한다. 전용 디렉터리는 tomcat:ssa-upload 2770, DB는 tomcat:ssa-upload 0660이다. 소스 디렉터리에 Tomcat 쓰기 권한을 추가하지 않았다. `scripts/prepare-flask-sqlite-linux.py`는 기본 읽기 전용이고 --apply는 별도 승인·root 인증이 필요하다. --resume은 기존 복사본의 무결성 및 원본과 스키마/데이터 동일성을 검사하고 기존 DB를 덮어쓰지 않는다. 이미 적용된 설정을 무조건 재실행하는 도구가 아니다.

실제 서비스의 Flask ON·AI 준비와 cuda:0, 세 상태 API HTTP 200을 확인했다. 운영 탐지 이벤트/Discord 실전송은 사용자 요청으로 보류했다. 구체적인 원인, 승인·적용 기록과 검증 범위는 [GPU 환경·운영 진단 기록](../project_ssa_yolo/GPU_ENVIRONMENT_LINUX.md)을 참고한다.
