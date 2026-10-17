package com.spring.service;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FlaskRuntimeControlServiceTest {

    @TempDir
    Path temporaryDirectory;

    private final Map<String, String> originalProperties = new HashMap<>();
    private final FlaskRuntimeControlService service = new FlaskRuntimeControlService();

    @BeforeEach
    void rememberSettings() {
        for (String name : new String[] { "SSA_FLASK_PROJECT_DIR", "SSA_FLASK_PYTHON_EXECUTABLE" }) {
            originalProperties.put(name, System.getProperty(name));
        }
    }

    @AfterEach
    void restoreSettings() {
        originalProperties.forEach((name, value) -> {
            if (value == null) {
                System.clearProperty(name);
            } else {
                System.setProperty(name, value);
            }
        });
    }

    @Test
    void acceptsAbsoluteAccessibleConfigurationWithoutRunningPythonOrContactingFlask() throws Exception {
        configureProjectAndExecutable();

        assertNull(service.projectConfigurationError());
    }

    @Test
    void rejectsRelativeAndMalformedProjectPathsInsteadOfUsingTomcatWorkingDirectory() throws Exception {
        configureProjectAndExecutable();
        for (String value : new String[] { ".", "relative/project", "bad\0path" }) {
            System.setProperty("SSA_FLASK_PROJECT_DIR", value);

            assertTrue(service.projectConfigurationError().contains("SSA_FLASK_PROJECT_DIR"));
        }
    }

    @Test
    void identifiesMissingEntryPointAndInvalidPythonExecutableSeparately() throws Exception {
        configureProjectAndExecutable();
        Files.delete(temporaryDirectory.resolve("run_server.py"));
        assertTrue(service.projectConfigurationError().contains("run_server.py"));

        Files.writeString(temporaryDirectory.resolve("run_server.py"), "test fixture; never executed");
        for (String value : new String[] { "python3", "bad\0path",
                temporaryDirectory.resolve("missing-python").toString(), temporaryDirectory.toString() }) {
            System.setProperty("SSA_FLASK_PYTHON_EXECUTABLE", value);
            String error = service.projectConfigurationError();

            assertNotNull(error);
            assertTrue(error.contains("SSA_FLASK_PYTHON_EXECUTABLE"));
        }
    }

    @Test
    void rejectsNonExecutablePythonFileOnLinux() throws Exception {
        assumeTrue(File.separatorChar == '/');
        Path executable = configureProjectAndExecutable();
        assertTrue(executable.toFile().setExecutable(false, false));

        assertTrue(service.projectConfigurationError().contains("SSA_FLASK_PYTHON_EXECUTABLE"));
    }

    private Path configureProjectAndExecutable() throws Exception {
        Files.writeString(temporaryDirectory.resolve("run_server.py"), "test fixture; never executed");
        Path executable = Files.writeString(temporaryDirectory.resolve("python-test-fixture"), "never executed");
        assumeTrue(executable.toFile().setExecutable(true), "The test filesystem does not support executable files.");
        System.setProperty("SSA_FLASK_PROJECT_DIR", temporaryDirectory.toString());
        System.setProperty("SSA_FLASK_PYTHON_EXECUTABLE", executable.toString());
        return executable;
    }
}
