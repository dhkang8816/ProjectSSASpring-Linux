package com.spring.util;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.io.File;
import java.nio.file.Path;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class RuntimeSettingsTest {

    @TempDir
    Path temporaryDirectory;

    private String originalUploadRoot;

    @BeforeEach
    void rememberUploadRoot() {
        originalUploadRoot = System.getProperty("SSA_UPLOAD_ROOT");
    }

    @AfterEach
    void restoreUploadRoot() {
        if (originalUploadRoot == null) {
            System.clearProperty("SSA_UPLOAD_ROOT");
        } else {
            System.setProperty("SSA_UPLOAD_ROOT", originalUploadRoot);
        }
    }

    @Test
    void usesPlatformSpecificDefaultWhenNotConfigured() {
        String environmentRoot = System.getenv("SSA_UPLOAD_ROOT");
        assumeTrue(environmentRoot == null || environmentRoot.isBlank());
        System.clearProperty("SSA_UPLOAD_ROOT");

        Path expected = Path.of(File.separatorChar == '\\' ? "C:\\upload" : "/var/lib/project-ssa/uploads");
        assertEquals(expected, RuntimeSettings.uploadRoot());
    }

    @Test
    void propertyOverridesEnvironmentAndNormalizesAbsolutePath() {
        System.setProperty("SSA_UPLOAD_ROOT", temporaryDirectory.resolve("old/../uploads").toString());

        assertEquals(temporaryDirectory.resolve("uploads"), RuntimeSettings.uploadRoot());
    }

    @Test
    void rejectsRelativeAndMalformedRoots() {
        System.setProperty("SSA_UPLOAD_ROOT", "relative/uploads");
        assertThrows(IllegalStateException.class, RuntimeSettings::uploadRoot);

        System.setProperty("SSA_UPLOAD_ROOT", "bad\0path");
        assertThrows(IllegalStateException.class, RuntimeSettings::uploadRoot);
    }

    @Test
    void rejectsWindowsPathOnLinuxInsteadOfUsingWorkingDirectory() {
        assumeTrue(File.separatorChar == '/');
        System.setProperty("SSA_UPLOAD_ROOT", "C:/upload");

        assertThrows(IllegalStateException.class, RuntimeSettings::uploadRoot);
    }
}
