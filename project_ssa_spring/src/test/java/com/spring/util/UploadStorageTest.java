package com.spring.util;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileSystemException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockServletContext;

class UploadStorageTest {

    private static final String BUNDLED_DEFAULT = "/resources/images/member/noImage.jpg";
    private static final byte[] DEFAULT_BYTES = { 5, 6, 7 };

    @TempDir
    Path temporaryDirectory;

    private String originalUploadRoot;

    @BeforeEach
    void configureUploadRoot() {
        originalUploadRoot = System.getProperty("SSA_UPLOAD_ROOT");
        System.setProperty("SSA_UPLOAD_ROOT", temporaryDirectory.resolve("uploads").toString());
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
    void resolvesCategoryWithoutCreatingDirectories() throws Exception {
        Path directory = UploadStorage.directory("member");

        assertEquals(temporaryDirectory.resolve("uploads/member").toFile().getCanonicalFile().toPath(), directory);
        assertTrue(directory.isAbsolute());
        assertFalse(Files.exists(directory));
        assertFalse(Files.exists(directory.getParent()));
    }

    @Test
    void rejectsPathBearingNamesAndPreservesLegacyBasenames() throws Exception {
        Path directory = UploadStorage.directory("member");
        for (String invalid : new String[] { "../outside.jpg", "..\\outside.jpg", "/tmp/outside.jpg",
                "C:outside.jpg", "", " ", ".", "..", "bad\0name.jpg" }) {
            assertThrows(IOException.class, () -> UploadStorage.resolveFile(directory, invalid), invalid);
        }

        String legacyName = "0123456789abcdef$$기존 직원 사진.JPG";
        assertEquals(directory.resolve(legacyName), UploadStorage.resolveFile(directory, legacyName));
    }

    @Test
    void rejectsCategorySymlinkEscapingRoot() throws Exception {
        Path root = Files.createDirectories(temporaryDirectory.resolve("uploads"));
        Path outside = Files.createDirectory(temporaryDirectory.resolve("outside"));
        createSymlink(root.resolve("member"), outside);

        assertThrows(IOException.class, () -> UploadStorage.directory("member"));
    }

    @Test
    void rejectsFileSymlinkOnReadAndDeleteWithoutTouchingItsTarget() throws Exception {
        Path directory = UploadStorage.createDirectory(UploadStorage.directory("member"));
        Path outside = Files.write(temporaryDirectory.resolve("outside.jpg"), new byte[] { 1, 2 });
        createSymlink(directory.resolve("linked.jpg"), outside);

        assertThrows(IOException.class, () -> UploadStorage.resolveFile(directory, "linked.jpg"));
        assertThrows(IOException.class, () -> UploadStorage.deleteFile(directory, "linked.jpg"));
        ResponseEntity<byte[]> response = UploadStorage.readImage(directory, "linked.jpg", bundledContext(), BUNDLED_DEFAULT);

        assertArrayEquals(DEFAULT_BYTES, response.getBody());
        assertArrayEquals(new byte[] { 1, 2 }, Files.readAllBytes(outside));
    }

    @Test
    void reportsDirectoryCreationFailure() throws Exception {
        Path regularFile = Files.write(temporaryDirectory.resolve("not-a-directory"), new byte[] { 1 });

        assertThrows(IOException.class, () -> UploadStorage.createDirectory(regularFile.resolve("member")));
    }

    @Test
    void readsActualImageWithItsMediaTypeThenExternalDefault() throws Exception {
        Path directory = UploadStorage.createDirectory(UploadStorage.directory("animals"));
        byte[] png = { 1, 3, 5 };
        Files.write(directory.resolve("animal.PNG"), png);
        Files.write(directory.resolve("noImage.jpg"), DEFAULT_BYTES);

        ResponseEntity<byte[]> response = UploadStorage.readImage(directory, "animal.PNG", bundledContext(), BUNDLED_DEFAULT);
        assertEquals(MediaType.IMAGE_PNG, response.getHeaders().getContentType());
        assertArrayEquals(png, response.getBody());
        assertArrayEquals(DEFAULT_BYTES,
                UploadStorage.readImage(directory, "missing.jpg", null, null).getBody());
    }

    @Test
    void readsBundledFallbackForUnsafeNameWithoutCreatingDirectories() throws Exception {
        Path directory = UploadStorage.directory("member");
        Files.write(temporaryDirectory.resolve("outside.jpg"), new byte[] { 1, 2 });

        ResponseEntity<byte[]> response = UploadStorage.readImage(directory, "../../outside.jpg", bundledContext(), BUNDLED_DEFAULT);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(MediaType.IMAGE_JPEG, response.getHeaders().getContentType());
        assertArrayEquals(DEFAULT_BYTES, response.getBody());
        assertFalse(Files.exists(directory.getParent()));
    }

    @Test
    void readsBundledFallbackWhenExternalStorageIsUnavailable() throws Exception {
        Path file = Files.write(temporaryDirectory.resolve("not-a-directory"), new byte[] { 1 });

        ResponseEntity<byte[]> response = UploadStorage.readImage(file.resolve("member"), "photo.jpg", bundledContext(), BUNDLED_DEFAULT);

        assertArrayEquals(DEFAULT_BYTES, response.getBody());
        assertArrayEquals(DEFAULT_BYTES, UploadStorage.readImage(null, null, bundledContext(), BUNDLED_DEFAULT).getBody());
    }

    @Test
    void returnsNotFoundWhenNeitherImageNorDefaultExists() throws Exception {
        ResponseEntity<byte[]> response = UploadStorage.readImage(UploadStorage.directory("member"), "missing.jpg", null, null);

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void deletesOnlyRequestedImageAndPreservesSharedDefault() throws Exception {
        Path directory = UploadStorage.createDirectory(UploadStorage.directory("member"));
        Files.write(directory.resolve("noImage.jpg"), DEFAULT_BYTES);
        Files.write(directory.resolve("legacy$$member.jpg"), new byte[] { 1 });

        UploadStorage.deleteFile(directory, null);
        UploadStorage.deleteFile(directory, "");
        UploadStorage.deleteFile(directory, "noImage.jpg");
        UploadStorage.deleteFile(directory, "legacy$$member.jpg");

        assertTrue(Files.exists(directory.resolve("noImage.jpg")));
        assertFalse(Files.exists(directory.resolve("legacy$$member.jpg")));
    }

    @Test
    void refusesToDeleteDirectoryMasqueradingAsImage() throws Exception {
        Path directory = UploadStorage.createDirectory(UploadStorage.directory("member"));
        Path imageDirectory = Files.createDirectory(directory.resolve("photo.jpg"));

        assertThrows(IOException.class, () -> UploadStorage.deleteFile(directory, "photo.jpg"));
        assertTrue(Files.isDirectory(imageDirectory));
    }

    private MockServletContext bundledContext() {
        return new MockServletContext() {
            @Override
            public InputStream getResourceAsStream(String path) {
                return BUNDLED_DEFAULT.equals(path) ? new ByteArrayInputStream(DEFAULT_BYTES) : null;
            }

            @Override
            public String getRealPath(String path) {
                return null; // A packed WAR need not expose a filesystem resource path.
            }
        };
    }

    private void createSymlink(Path link, Path target) throws IOException {
        try {
            Files.createSymbolicLink(link, target);
        } catch (UnsupportedOperationException | SecurityException ex) {
            if (File.separatorChar == '\\') {
                assumeTrue(false, "Windows symbolic links are unavailable: " + ex.getMessage());
            }
            throw ex;
        } catch (FileSystemException ex) {
            String reason = String.valueOf(ex.getReason()).toLowerCase(Locale.ROOT);
            if (File.separatorChar == '\\' && (ex instanceof AccessDeniedException
                    || reason.contains("privilege") || reason.contains("not supported"))) {
                assumeTrue(false, "Windows symbolic links are unavailable: " + ex.getMessage());
            }
            throw ex;
        }
    }
}
