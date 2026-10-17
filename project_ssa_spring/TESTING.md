# Spring test guide

Earlier GPU control verification: `mvn -o verify` with the opt-in isolated GPU
test enabled passed **118 tests, 0 failures/errors, 1 Windows-only skip**.
`FlaskRuntimeReadinessTest` checks HTTP/AI state separation and, only when
`SSA_RUN_GPU_INTEGRATION=true`, a real local venv Flask process using CUDA.
The GPU test is skipped in normal builds. The wrapper
`scripts/check-flask-gpu.py` uses the AI profile without SQLite and a temporary token/port,
disables device/notification workers and never deploys to Tomcat. See
[the GPU guide](../project_ssa_yolo/GPU_ENVIRONMENT_LINUX.md).

Run Spring unit tests from this directory after Maven is available:

```powershell
mvn test
```

Linux also supports `mvn -o verify` when dependencies are already cached. This
runs the unit suite and packages the WAR; it does not deploy or restart Tomcat.
The package phase checks that the local JDBC resource is present without
displaying its contents. Unit tests do not need actual database credentials.

Path regression tests cover OS upload/cache defaults and overrides, deferred PDF
cache configuration, browser discovery, and Flask project/Python validation.
They use temporary files and mocked DAOs, without executing Python or browsers.

2026-10-17 path-change verification: Java 17, `mvn -o verify` **BUILD SUCCESS**;
115 tests, 0 failures, 0 errors, 1 Windows-only test skipped on Linux. The initial
sandbox run blocked Mockito JVM self-attachment; the approved unrestricted
offline build passed. WAR placement of the existing JDBC resource was checked
without printing values. These results do not validate production permissions
or actual PDF browser rendering. See [the path audit](../PATH_CONFIGURATION_LINUX.md).

The diagnostics tests mock the datasource, environment lookup and HTTP client.
They do not connect to Oracle, Flask, ESP32, Discord, Kakao, Open-Meteo or NOAA.

Manual diagnostics smoke test:

1. Log in with an account that has `ROLE_ADMIN`.
2. Open `/admin/diagnostics`.
3. Confirm that the status table is populated by `GET /admin/diagnostics/all`.
4. Confirm the page causes no buzzer sound, Discord message, camera startup or detection action.

## 운영 계정 권한 회귀 검사

권한 정상화 시 `mvn -o verify`는 120 tests, 0 failures/errors, 2 skips로 통과했다.
POSIX spool 이동 후 새 업로드 파일의 그룹·0660 검사를 기존 MultipartFileUploadTest에 추가했다.
실제 배포된 helper의 임시 PNG 저장·재조회와 Oracle SELECT, 서비스 namespace GPU 검사는
[Linux 실행 권한 안내](../LINUX_RUNTIME_PERMISSIONS.md)의 별도 관리자 진단 도구로 수행했다.
이 결과를 인증된 회원 화면의 HTTP 업로드/DB 변경이나 PDF 브라우저 렌더링 성공으로 해석하지 않는다.
