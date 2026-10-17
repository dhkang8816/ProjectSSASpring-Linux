package com.spring.service;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.spring.util.RuntimeSettings;

/**
 * Controls only the locally configured Flask runtime.  No request parameter is
 * ever used as a command or executable path, and stopping is performed through
 * Flask's token-protected shutdown endpoint instead of killing arbitrary
 * Python processes.
 */
public class FlaskRuntimeControlService {

    private static final int HEALTH_TIMEOUT_MS = 1500;
    private static final int CONTROL_TIMEOUT_MS = 3000;

    private final Object processMonitor = new Object();
    private final ObjectMapper objectMapper = new ObjectMapper();
    private volatile Process managedProcess;
    private volatile long lastStartRequestedAt;
    private volatile boolean startupRequested;
    private volatile boolean startupInitializationRequested;

    public Map<String, Object> status() {
        boolean online = isFlaskOnline();
        boolean enabled = RuntimeSettings.enabled("SSA_FLASK_CONTROL_ENABLED", false);
        boolean localTarget = isLocalFlaskTarget();
        boolean projectReady = isProjectReady();
        boolean tokenReady = hasControlToken();
        boolean managedProcessAlive = isManagedProcessAlive();
        StartupState startup = resolveStartupState(online, managedProcessAlive);
        if (online && startup.ready) {
            startupRequested = false;
            startupInitializationRequested = false;
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("online", online);
        result.put("controlEnabled", enabled);
        result.put("managedProcess", managedProcessAlive);
        result.put("canStart", enabled && localTarget && projectReady && tokenReady && !online && !managedProcessAlive);
        result.put("canStop", enabled && localTarget && tokenReady && online);
        result.put("startupInProgress", startupRequested && !startup.ready);
        result.put("startupStage", startup.stage);
        result.put("startupProgress", startup.progress);
        result.put("startupLabel", startup.label);
        result.put("startupElapsedMillis", startupRequested
                ? Math.max(0L, System.currentTimeMillis() - lastStartRequestedAt) : 0L);
        result.put("message", statusMessage(online, enabled, localTarget, projectReady, tokenReady));
        return result;
    }

    public Map<String, Object> start() {
        synchronized (processMonitor) {
            if (isFlaskOnline()) {
                return actionResult(false, "ALREADY_ONLINE", "Flask 서버가 이미 실행 중입니다.");
            }
            String configurationError = startConfigurationError();
            if (configurationError != null) {
                return actionResult(false, "CONFIGURATION_REQUIRED", configurationError);
            }
            if (isManagedProcessAlive()) {
                return actionResult(false, "STARTING", "Flask 시작 프로세스가 이미 실행 중입니다.");
            }

            try {
                ProcessBuilder processBuilder = new ProcessBuilder(
                        configuredAbsolutePath("SSA_FLASK_PYTHON_EXECUTABLE").toString(), "run_server.py");
                processBuilder.directory(projectDirectory().toFile());
                processBuilder.redirectErrorStream(true);
                processBuilder.redirectOutput(ProcessBuilder.Redirect.INHERIT);
                managedProcess = processBuilder.start();
                lastStartRequestedAt = System.currentTimeMillis();
                startupRequested = true;
                startupInitializationRequested = false;
                return actionResult(true, "START_REQUESTED", "Flask 시작을 요청했습니다. 상태 확인을 기다립니다.");
            } catch (IOException | IllegalStateException | SecurityException error) {
                return actionResult(false, "START_FAILED", "Flask를 시작하지 못했습니다. Python 실행 경로와 프로젝트 경로를 확인하세요.");
            }
        }
    }

    public Map<String, Object> stop() {
        synchronized (processMonitor) {
            startupRequested = false;
            startupInitializationRequested = false;
            if (!isFlaskOnline()) {
                return actionResult(false, "ALREADY_OFFLINE", "Flask 서버가 이미 중지되어 있습니다.");
            }
            String configurationError = controlConfigurationError();
            if (configurationError != null) {
                return actionResult(false, "CONFIGURATION_REQUIRED", configurationError);
            }

            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) URI.create(controlUrl()).toURL().openConnection();
                connection.setRequestMethod("POST");
                connection.setConnectTimeout(CONTROL_TIMEOUT_MS);
                connection.setReadTimeout(CONTROL_TIMEOUT_MS);
                connection.setDoOutput(true);
                connection.setRequestProperty("X-SSA-Flask-Control-Token",
                        RuntimeSettings.text("SSA_FLASK_CONTROL_TOKEN", ""));
                int status = connection.getResponseCode();
                if (status >= 200 && status < 300) {
                    return actionResult(true, "STOP_REQUESTED", "Flask 정상 종료를 요청했습니다.");
                }
                return actionResult(false, "STOP_REJECTED", "Flask 종료 요청이 거부되었습니다. 제어 토큰을 확인하세요.");
            } catch (Exception error) {
                return actionResult(false, "STOP_FAILED", "Flask 종료 요청에 실패했습니다. 서버 연결 상태를 확인하세요.");
            } finally {
                if (connection != null) {
                    connection.disconnect();
                }
            }
        }
    }

    private Map<String, Object> actionResult(boolean success, String action, String message) {
        Map<String, Object> result = status();
        result.put("success", success);
        result.put("action", action);
        result.put("message", message);
        return result;
    }

    private boolean isFlaskOnline() {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) URI.create(healthUrl()).toURL().openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(HEALTH_TIMEOUT_MS);
            connection.setReadTimeout(HEALTH_TIMEOUT_MS);
            int status = connection.getResponseCode();
            return status >= 200 && status < 300;
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private boolean isManagedProcessAlive() {
        Process process = managedProcess;
        if (process != null && !process.isAlive()) {
            managedProcess = null;
            process = null;
        }
        return process != null;
    }

    private String startupStage(boolean online, boolean managedProcessAlive) {
        if (online) {
            return "READY";
        }
        if (managedProcessAlive) {
            return "PROCESS_RUNNING";
        }
        return startupRequested ? "START_FAILED" : "IDLE";
    }

    private int startupProgress(boolean online, boolean managedProcessAlive) {
        if (online) {
            return 100;
        }
        if (managedProcessAlive) {
            return 55;
        }
        return 0;
    }

    private String startupLabel(boolean online, boolean managedProcessAlive) {
        if (online) {
            return "Flask 상태 API 응답 확인 완료";
        }
        if (managedProcessAlive) {
            return "Python 프로세스 실행 확인";
        }
        if (startupRequested) {
            return "Python 프로세스가 종료되었습니다";
        }
        return "Flask 서버 대기";
    }

    /**
     * The HTTP health endpoint only proves that the Flask web process is
     * listening. During a managed start, additionally ask Flask to start its
     * optional workers and surface its own step-by-step lifecycle state.
     */
    private StartupState resolveStartupState(boolean online, boolean managedProcessAlive) {
        if (!online) {
            if (managedProcessAlive) {
                return new StartupState("PROCESS_RUNNING", 55, "Python 프로세스 실행 확인", false);
            }
            if (startupRequested) {
                return new StartupState("START_FAILED", 0, "Python 프로세스가 종료되었습니다", false);
            }
            return new StartupState("IDLE", 0, "Flask 서버 대기", false);
        }

        if (!startupRequested) {
            return new StartupState("READY", 100, "Flask 상태 API 응답 확인 완료", true);
        }

        StartupState state = startupInitializationRequested
                ? requestFlaskStartupState(false)
                : requestFlaskStartupState(true);
        if (!startupInitializationRequested && !"SERVICE_FAILED".equals(state.stage)) {
            startupInitializationRequested = true;
        }
        return state;
    }

    private StartupState requestFlaskStartupState(boolean initialize) {
        HttpURLConnection connection = null;
        try {
            String path = initialize ? "/admin/initialize" : "/admin/startup-status";
            connection = (HttpURLConnection) URI.create(streamBaseUrl() + path).toURL().openConnection();
            connection.setRequestMethod(initialize ? "POST" : "GET");
            connection.setConnectTimeout(CONTROL_TIMEOUT_MS);
            connection.setReadTimeout(CONTROL_TIMEOUT_MS);
            connection.setRequestProperty("X-SSA-Flask-Control-Token",
                    RuntimeSettings.text("SSA_FLASK_CONTROL_TOKEN", ""));
            if (initialize) {
                connection.setDoOutput(true);
            }

            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) {
                return new StartupState("SERVICE_FAILED", 0, "Flask 부가 서비스 상태 확인 실패", false);
            }

            JsonNode payload = objectMapper.readTree(
                    new String(connection.getInputStream().readAllBytes(), StandardCharsets.UTF_8));
            if (!"SUCCESS".equals(payload.path("status").asText())) {
                return new StartupState("SERVICE_FAILED", 0, "Flask 부가 서비스 시작 요청이 거부되었습니다", false);
            }

            String stage = payload.path("stage").asText("SERVICES_STARTING");
            int progress = payload.path("progress").asInt(70);
            String label = payload.path("label").asText("부가 서비스 시작 중");
            boolean ready = payload.path("ready").asBoolean(false);
            return new StartupState(stage, progress, label, ready);
        } catch (Exception ignored) {
            return new StartupState("SERVICE_FAILED", 0, "Flask 부가 서비스 상태 확인 실패", false);
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private static final class StartupState {
        private final String stage;
        private final int progress;
        private final String label;
        private final boolean ready;

        private StartupState(String stage, int progress, String label, boolean ready) {
            this.stage = stage;
            this.progress = progress;
            this.label = label;
            this.ready = ready;
        }
    }

    private String statusMessage(boolean online, boolean enabled, boolean localTarget,
            boolean projectReady, boolean tokenReady) {
        if (online) {
            if (!enabled) {
                return "Flask 서버는 실행 중이지만 제어 기능이 비활성화되어 있습니다.";
            }
            if (!localTarget) {
                return "Flask 서버는 실행 중이지만 원격 주소는 이 화면에서 제어할 수 없습니다.";
            }
            if (!tokenReady) {
                return "Flask 서버는 실행 중이지만 제어 토큰 설정이 필요합니다.";
            }
            return "Flask 서버가 실행 중입니다.";
        }
        if (!enabled) {
            return "Flask 제어 기능이 비활성화되어 있습니다.";
        }
        if (!localTarget) {
            return "원격 Flask 주소는 이 화면에서 제어할 수 없습니다.";
        }
        if (!projectReady) {
            return projectConfigurationError();
        }
        if (!tokenReady) {
            return "Flask 제어 토큰 설정이 필요합니다.";
        }
        return "Flask 서버가 중지되어 있습니다.";
    }

    private String controlConfigurationError() {
        if (!RuntimeSettings.enabled("SSA_FLASK_CONTROL_ENABLED", false)) {
            return "SSA_FLASK_CONTROL_ENABLED=true 설정이 필요합니다.";
        }
        if (!isLocalFlaskTarget()) {
            return "보안을 위해 localhost Flask 서버만 이 화면에서 제어할 수 있습니다.";
        }
        if (!hasControlToken()) {
            return "SSA_FLASK_CONTROL_TOKEN 설정이 필요합니다.";
        }
        return null;
    }

    private String startConfigurationError() {
        String controlError = controlConfigurationError();
        if (controlError != null) {
            return controlError;
        }
        return projectConfigurationError();
    }

    private boolean isProjectReady() {
        return projectConfigurationError() == null;
    }

    String projectConfigurationError() {
        try {
            Path project = projectDirectory();
            if (!Files.isDirectory(project) || !Files.isReadable(project) || !Files.isExecutable(project)) {
                return "SSA_FLASK_PROJECT_DIR에 접근 가능한 프로젝트 디렉터리의 절대경로를 설정하세요.";
            }
            Path entryPoint = project.resolve("run_server.py");
            if (!Files.isRegularFile(entryPoint) || !Files.isReadable(entryPoint)) {
                return "SSA_FLASK_PROJECT_DIR 안에 읽을 수 있는 run_server.py가 필요합니다.";
            }
            Path executable = configuredAbsolutePath("SSA_FLASK_PYTHON_EXECUTABLE");
            if (!Files.isRegularFile(executable) || !Files.isReadable(executable) || !Files.isExecutable(executable)) {
                return "SSA_FLASK_PYTHON_EXECUTABLE에 읽고 실행할 수 있는 Python 파일의 절대경로를 설정하세요.";
            }
            return null;
        } catch (IllegalStateException ex) {
            return ex.getMessage();
        } catch (SecurityException ex) {
            return "SSA_FLASK_PROJECT_DIR 및 SSA_FLASK_PYTHON_EXECUTABLE 접근 권한을 확인하세요.";
        }
    }

    private boolean hasControlToken() {
        String token = RuntimeSettings.text("SSA_FLASK_CONTROL_TOKEN", "");
        return token.length() >= 24 && !token.contains("CHANGE_ME");
    }

    private boolean isLocalFlaskTarget() {
        try {
            String host = URI.create(streamBaseUrl()).getHost();
            return "localhost".equalsIgnoreCase(host) || "127.0.0.1".equals(host) || "::1".equals(host);
        } catch (Exception ignored) {
            return false;
        }
    }

    private Path projectDirectory() {
        return configuredAbsolutePath("SSA_FLASK_PROJECT_DIR");
    }

    private static Path configuredAbsolutePath(String name) {
        String configured = RuntimeSettings.text(name, "");
        if (configured.isBlank()) {
            throw new IllegalStateException(name + "에 절대경로를 설정하세요.");
        }
        try {
            Path path = Path.of(configured);
            if (!path.isAbsolute()) {
                throw new IllegalStateException(name + "에는 현재 OS에서 유효한 절대경로가 필요합니다.");
            }
            return path.normalize();
        } catch (InvalidPathException ex) {
            throw new IllegalStateException(name + "의 경로 형식이 올바르지 않습니다.");
        }
    }

    private String streamBaseUrl() {
        String value = RuntimeSettings.text("SSA_FLASK_STREAM_URL", "http://localhost:5000/stream");
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }

    private String healthUrl() {
        return streamBaseUrl() + "/health";
    }

    private String controlUrl() {
        return streamBaseUrl() + "/admin/shutdown";
    }
}
