package com.spring.util;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

class MultipartFileUploadTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void normalizesRenamedSpoolPermissionsToTheDestinationDirectoryGroup() throws Exception {
        org.junit.jupiter.api.Assumptions.assumeTrue(
                Files.getFileStore(temporaryDirectory).supportsFileAttributeView("posix"));
        MockMultipartFile image = new MockMultipartFile("pictureFile", "probe.png", "image/png", new byte[] {1}) {
            @Override
            public void transferTo(File destination) throws IOException {
                Path spool = Files.createTempFile(temporaryDirectory, "spool-", ".tmp");
                Files.write(spool, getBytes());
                Files.setPosixFilePermissions(spool, java.nio.file.attribute.PosixFilePermissions.fromString("rw-------"));
                Files.move(spool, destination.toPath());
            }
        };
        String name = MultipartFileUpload.saveImageFile(temporaryDirectory.toString(), image);
        assertEquals("rw-rw----", java.nio.file.attribute.PosixFilePermissions.toString(
                Files.getPosixFilePermissions(temporaryDirectory.resolve(name))));
        assertEquals(Files.readAttributes(temporaryDirectory, java.nio.file.attribute.PosixFileAttributes.class).group(),
                Files.readAttributes(temporaryDirectory.resolve(name), java.nio.file.attribute.PosixFileAttributes.class).group());
    }

    @Test
    void savesAllowedImageWithServerGeneratedFileName() throws Exception {
        byte[] imageBytes = { 1, 2, 3 };
        MockMultipartFile image = new MockMultipartFile(
                "pictureFile", "../../dog.jpg", "image/jpeg", imageBytes);

        String savedName = MultipartFileUpload.saveImageFile(temporaryDirectory.toString(), image);

        assertTrue(savedName.matches("^[0-9a-f]{32}\\.jpg$"));
        assertArrayEquals(imageBytes, Files.readAllBytes(temporaryDirectory.resolve(savedName)));
    }

    @Test
    void rejectsNonImageExtensionAndContentType() {
        MockMultipartFile executable = new MockMultipartFile(
                "pictureFile", "script.exe", "application/octet-stream", new byte[] { 1 });

        assertThrows(IllegalArgumentException.class,
                () -> MultipartFileUpload.saveImageFile(temporaryDirectory.toString(), executable));
    }

    @Test
    void preservesMemberFilenameFormatAndTransfersToCanonicalAbsoluteFile() throws Exception {
        AtomicReference<File> destination = new AtomicReference<>();
        MockMultipartFile image = new MockMultipartFile(
                "pictureFile", "직원 사진.JPG", "image/jpeg", new byte[] { 1, 2 }) {
            @Override
            public void transferTo(File file) throws IOException {
                destination.set(file);
                super.transferTo(file);
            }
        };
        Path directory = temporaryDirectory.resolve("new/../member");

        String savedName = MultipartFileUpload.saveFile(directory.toString(), image);

        assertTrue(savedName.matches("[0-9a-f]{32}\\$\\$직원 사진\\.JPG"));
        assertTrue(destination.get().isAbsolute());
        assertEquals(destination.get().getCanonicalFile(), destination.get());
        assertArrayEquals(new byte[] { 1, 2 }, Files.readAllBytes(destination.get().toPath()));
    }

    @Test
    void rejectsPathBearingMemberOriginalBeforeCreatingDirectory() {
        Path directory = temporaryDirectory.resolve("member");
        for (String name : new String[] { "../outside.jpg", "..\\outside.jpg", "C:outside.jpg", "", ".." }) {
            MockMultipartFile image = new MockMultipartFile("pictureFile", name, "image/jpeg", new byte[] { 1 });

            assertThrows(IOException.class, () -> MultipartFileUpload.saveFile(directory.toString(), image));
        }
        assertFalse(Files.exists(directory));
    }

    @Test
    void validatesOldMemberNameBeforeUploadingReplacement() throws Exception {
        MockMultipartFile image = new MockMultipartFile("pictureFile", "new.jpg", "image/jpeg", new byte[] { 1 });
        Path outside = Files.write(temporaryDirectory.resolve("outside.jpg"), new byte[] { 4 });
        Path directory = temporaryDirectory.resolve("member");

        assertThrows(IOException.class,
                () -> MultipartFileUpload.saveFile(directory.toString(), "../outside.jpg", image));

        assertFalse(Files.exists(directory));
        assertArrayEquals(new byte[] { 4 }, Files.readAllBytes(outside));
    }

    @Test
    void replacesLegacyMemberPhotoAndKeepsDefaultPhoto() throws Exception {
        String oldName = "legacy$$직원 사진.jpg";
        Files.write(temporaryDirectory.resolve(oldName), new byte[] { 4 });
        Files.write(temporaryDirectory.resolve("noImage.jpg"), new byte[] { 5 });
        MockMultipartFile image = new MockMultipartFile("pictureFile", "new.jpg", "image/jpeg", new byte[] { 1 });

        String savedName = MultipartFileUpload.saveFile(temporaryDirectory.toString(), oldName, image);
        assertFalse(Files.exists(temporaryDirectory.resolve(oldName)));
        assertTrue(Files.exists(temporaryDirectory.resolve(savedName)));

        MultipartFileUpload.saveFile(temporaryDirectory.toString(), "noImage.jpg", image);
        assertArrayEquals(new byte[] { 5 }, Files.readAllBytes(temporaryDirectory.resolve("noImage.jpg")));
    }

    @Test
    void reportsUploadDirectoryCreationFailure() throws Exception {
        Path file = Files.write(temporaryDirectory.resolve("not-a-directory"), new byte[] { 1 });
        MockMultipartFile image = new MockMultipartFile("pictureFile", "new.jpg", "image/jpeg", new byte[] { 1 });

        assertThrows(IOException.class, () -> MultipartFileUpload.saveFile(file.resolve("member").toString(), image));
        assertThrows(IOException.class, () -> MultipartFileUpload.saveImageFile(file.resolve("animals").toString(), image));
    }

    @Test
    void failedTransferRemovesPartialUploadAndPreservesOldPhoto() throws Exception {
        String oldName = "legacy$$old.jpg";
        Path oldPhoto = Files.write(temporaryDirectory.resolve(oldName), new byte[] { 5, 6 });
        MockMultipartFile image = new MockMultipartFile("pictureFile", "new.jpg", "image/jpeg", new byte[] { 1, 2 }) {
            @Override
            public void transferTo(File file) throws IOException {
                Files.write(file.toPath(), new byte[] { 1 });
                throw new IOException("Simulated interrupted upload");
            }
        };

        assertThrows(IOException.class,
                () -> MultipartFileUpload.saveFile(temporaryDirectory.toString(), oldName, image));

        assertArrayEquals(new byte[] { 5, 6 }, Files.readAllBytes(oldPhoto));
        try (Stream<Path> files = Files.list(temporaryDirectory)) {
            assertEquals(List.of(oldPhoto), files.toList());
        }
    }
}
