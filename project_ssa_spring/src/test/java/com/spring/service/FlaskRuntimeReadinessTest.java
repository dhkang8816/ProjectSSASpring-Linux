package com.spring.service;

import static org.junit.jupiter.api.Assertions.*;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import com.sun.net.httpserver.HttpServer;

class FlaskRuntimeReadinessTest {
    private final Map<String, String> original = new HashMap<>();
    private HttpServer fixture;

    @BeforeEach
    void saveProperties() {
        for (String name : new String[] {"SSA_FLASK_STREAM_URL", "SSA_FLASK_CONTROL_TOKEN",
                "SSA_FLASK_CONTROL_ENABLED", "SSA_FLASK_PROJECT_DIR", "SSA_FLASK_PYTHON_EXECUTABLE"}) {
            original.put(name, System.getProperty(name));
        }
    }

    @AfterEach
    void restoreProperties() {
        if (fixture != null) fixture.stop(0);
        original.forEach((name, value) -> {
            if (value == null) System.clearProperty(name);
            else System.setProperty(name, value);
        });
    }

    @Test
    void httpSuccessDoesNotClaimAiReadiness() throws Exception {
        AtomicReference<String> body = fixture();
        body.set("{\"status\":\"SUCCESS\",\"ready\":true,\"stage\":\"AI_FAILED\",\"aiReady\":false}");
        Map<String, Object> status = new FlaskRuntimeControlService().status();
        assertEquals(true, status.get("processReady"));
        assertEquals(false, status.get("aiReady"));
        assertEquals("AI_FAILED", status.get("startupStage"));
    }

    @Test
    void reportsAiReadinessOnlyWhenFlaskExplicitlyConfirmsIt() throws Exception {
        AtomicReference<String> body = fixture();
        body.set("{\"status\":\"SUCCESS\",\"ready\":true,\"stage\":\"READY\",\"aiReady\":true}");
        assertEquals(true, new FlaskRuntimeControlService().status().get("aiReady"));
    }

    @Test
    void readsActualAiHealthWithoutControlTokenOrProtectedApi() throws Exception {
        AtomicReference<String> body = fixture();
        System.setProperty("SSA_FLASK_CONTROL_TOKEN", "");
        body.set("{\"ai\":{\"ready\":true,\"stage\":\"AI_READY\",\"device\":\"cuda:0\"}}");
        fixture.removeContext("/stream/admin/startup-status");
        Map<String, Object> status = new FlaskRuntimeControlService().status();
        assertEquals(true, status.get("aiReady"));
        assertEquals(true, status.get("ready"));
        body.set("{\"ai\":{\"ready\":false,\"stage\":\"AI_FAILED\",\"error\":\"CUDA unavailable\"}}");
        status = new FlaskRuntimeControlService().status();
        assertEquals(false, status.get("aiReady"));
        assertEquals("CUDA unavailable", status.get("aiError"));
    }

    private AtomicReference<String> fixture() throws Exception {
        AtomicReference<String> body = new AtomicReference<>();
        fixture = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        fixture.createContext("/stream/health", exchange -> {
            byte[] data = body.get().getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, data.length);
            try (var output = exchange.getResponseBody()) { output.write(data); }
        });
        fixture.createContext("/stream/admin/startup-status", exchange -> {
            byte[] data = body.get().getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, data.length);
            try (var output = exchange.getResponseBody()) { output.write(data); }
        });
        fixture.start();
        System.setProperty("SSA_FLASK_STREAM_URL", "http://127.0.0.1:" + fixture.getAddress().getPort() + "/stream");
        System.setProperty("SSA_FLASK_CONTROL_TOKEN", "x".repeat(32));
        return body;
    }

    @Test
    @EnabledIfEnvironmentVariable(named = "SSA_RUN_GPU_INTEGRATION", matches = "true")
    void startsRealVenvFlaskWarmsGpuRejectsDuplicateAndStopsOwnedProcess() throws Exception {
        Path project = Path.of(System.getenv("SSA_GPU_TEST_PROJECT_DIR"));
        System.setProperty("SSA_FLASK_STREAM_URL", "http://127.0.0.1:" + System.getenv("FLASK_RUN_PORT") + "/stream");
        System.setProperty("SSA_FLASK_CONTROL_ENABLED", "true");
        System.setProperty("SSA_FLASK_CONTROL_TOKEN", System.getenv("SSA_FLASK_CONTROL_TOKEN"));
        System.setProperty("SSA_FLASK_PROJECT_DIR", project.toString());
        System.setProperty("SSA_FLASK_PYTHON_EXECUTABLE", project.resolve(".venv/bin/python").toString());
        FlaskRuntimeControlService service = new FlaskRuntimeControlService();
        try {
            Object previousInstance = null;
            for (int cycle = 0; cycle < 2; cycle++) {
                assertEquals("START_REQUESTED", service.start().get("action"));
                long deadline = System.nanoTime() + Duration.ofSeconds(45).toNanos();
                Map<String, Object> status;
                do {
                    status = service.status();
                    if (Boolean.TRUE.equals(status.get("aiReady"))) break;
                    assertNotEquals("AI_FAILED", status.get("startupStage"));
                    Thread.sleep(100);
                } while (System.nanoTime() < deadline);
                assertEquals(true, status.get("processReady"));
                assertEquals(true, status.get("aiReady"));
                assertEquals(true, status.get("ready"));
                assertNotNull(status.get("instanceId"));
                assertNotEquals(previousInstance, status.get("instanceId"));
                previousInstance = status.get("instanceId");
                assertEquals("ALREADY_ONLINE", service.start().get("action"));
                assertEquals("STOP_REQUESTED", service.stop().get("action"));
                deadline = System.nanoTime() + Duration.ofSeconds(15).toNanos();
                do {
                    status = service.status();
                    if (Boolean.FALSE.equals(status.get("managedProcess")) && Boolean.FALSE.equals(status.get("online"))) break;
                    Thread.sleep(100);
                } while (System.nanoTime() < deadline);
                assertEquals(false, status.get("online"));
                assertEquals(false, status.get("managedProcess"));
            }
            System.out.println("GPU integration: two start/AI-ready/duplicate-rejected/stop cycles passed");
        } finally {
            // Cleanup is limited to the exact child created by this test instance.
            var field = FlaskRuntimeControlService.class.getDeclaredField("managedProcess");
            field.setAccessible(true);
            Process child = (Process) field.get(service);
            if (child != null && child.isAlive()) {
                child.destroy();
                if (!child.waitFor(3, TimeUnit.SECONDS)) child.destroyForcibly().waitFor(3, TimeUnit.SECONDS);
            }
        }
    }
}
