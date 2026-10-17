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
    private String originalCacheRoot;

    @BeforeEach
    void rememberUploadRoot() {
        originalUploadRoot = System.getProperty("SSA_UPLOAD_ROOT");
        originalCacheRoot = System.getProperty("SSA_CACHE_ROOT");
    }

    @AfterEach
    void restoreUploadRoot() {
        if (originalUploadRoot == null) {
            System.clearProperty("SSA_UPLOAD_ROOT");
        } else {
            System.setProperty("SSA_UPLOAD_ROOT", originalUploadRoot);
        }
        if (originalCacheRoot == null) {
            System.clearProperty("SSA_CACHE_ROOT");
        } else {
            System.setProperty("SSA_CACHE_ROOT", originalCacheRoot);
        }
    }

    @Test
    void retainsWindowsDevelopmentDefaultWhenNotConfigured() {
        assumeTrue(File.separatorChar == '\\');
        String environmentRoot = System.getenv("SSA_UPLOAD_ROOT");
        assumeTrue(environmentRoot == null || environmentRoot.isBlank());
        System.clearProperty("SSA_UPLOAD_ROOT");

        Path expected = Path.of("C:\\upload");
        assertEquals(expected, RuntimeSettings.uploadRoot());
    }

    @Test
    void providesLinuxUploadDefaultWithoutCreatingDirectories() {
        assumeTrue(File.separatorChar == '/');
        String environmentRoot = System.getenv("SSA_UPLOAD_ROOT");
        assumeTrue(environmentRoot == null || environmentRoot.isBlank());
        System.clearProperty("SSA_UPLOAD_ROOT");

        assertEquals(Path.of("/var/lib/project-ssa/uploads"), RuntimeSettings.uploadRoot());
    }

    @Test
    void keepsLinuxCacheSeparateAndAllowsAnExplicitOverride() {
        assumeTrue(File.separatorChar == '/');
        String environmentCache = System.getenv("SSA_CACHE_ROOT");
        assumeTrue(environmentCache == null || environmentCache.isBlank());
        System.clearProperty("SSA_CACHE_ROOT");
        System.setProperty("SSA_UPLOAD_ROOT", temporaryDirectory.resolve("uploads").toString());
        assertEquals(Path.of("/var/cache/project-ssa"), RuntimeSettings.cacheRoot());

        System.setProperty("SSA_CACHE_ROOT", temporaryDirectory.resolve("cache").toString());
        assertEquals(temporaryDirectory.resolve("cache"), RuntimeSettings.cacheRoot());
        System.setProperty("SSA_CACHE_ROOT", "relative/cache");
        assertThrows(IllegalStateException.class, RuntimeSettings::cacheRoot);
    }

    @Test
    void explicitCacheRootDoesNotDependOnAnUnrelatedInvalidUploadSetting() {
        System.setProperty("SSA_UPLOAD_ROOT", "invalid/relative/uploads");
        System.setProperty("SSA_CACHE_ROOT", temporaryDirectory.toString());

        assertEquals(temporaryDirectory, RuntimeSettings.cacheRoot());
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
