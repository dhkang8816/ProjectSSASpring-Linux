# Spring test guide

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
