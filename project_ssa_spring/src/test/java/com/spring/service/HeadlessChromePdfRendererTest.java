package com.spring.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class HeadlessChromePdfRendererTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void explicitlyConfiguredBrowserTakesPrecedenceWithoutStartingIt() throws Exception {
        Path browser = executable("configured-browser");
        Path pathDirectory = Files.createDirectory(temporaryDirectory.resolve("bin"));
        executable("bin/chromium");

        assertEquals(browser, HeadlessChromePdfRenderer.resolveBrowserExecutable(
                browser.toString(), pathDirectory.toString(), false));
    }

    @Test
    void invalidExplicitBrowserDoesNotFallBackToAnAvailableBrowser() throws Exception {
        Path available = executable("chromium");

        for (String invalid : new String[] { "relative/chrome", "bad\0path",
                temporaryDirectory.resolve("missing-browser").toString(), temporaryDirectory.toString() }) {
            IOException error = assertThrows(IOException.class, () -> HeadlessChromePdfRenderer.resolveBrowserExecutable(
                    invalid, available.getParent().toString(), false));
            assertTrue(error.getMessage().contains("SSA_PDF_BROWSER_PATH"));
        }
    }

    @Test
    void discoversLinuxBrowserOnlyInAbsolutePathEntries() throws Exception {
        assumeTrue(File.separatorChar == '/');
        Path browser = executable("chromium");
        String searchPath = "." + File.pathSeparator + "" + File.pathSeparator + temporaryDirectory;

        assertEquals(browser, HeadlessChromePdfRenderer.resolveBrowserExecutable("", searchPath, false));
        assertThrows(IOException.class,
                () -> HeadlessChromePdfRenderer.resolveBrowserExecutable("", ".", false));
    }

    @Test
    void rejectsExplicitNonExecutableFileOnLinux() throws Exception {
        assumeTrue(File.separatorChar == '/');
        Path file = Files.writeString(temporaryDirectory.resolve("not-executable"), "test fixture");
        assertTrue(file.toFile().setExecutable(false, false));

        assertThrows(IOException.class,
                () -> HeadlessChromePdfRenderer.resolveBrowserExecutable(file.toString(), "", false));
    }

    private Path executable(String relativePath) throws IOException {
        Path file = Files.writeString(temporaryDirectory.resolve(relativePath), "test fixture; never executed");
        assumeTrue(file.toFile().setExecutable(true), "The test filesystem does not support executable files.");
        return file;
    }
}
