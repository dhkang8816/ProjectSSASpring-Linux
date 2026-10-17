package com.spring.util;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Locale;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import jakarta.servlet.ServletContext;

/** Shared storage paths for uploaded photos and externally produced snapshots. */
public final class UploadStorage {

    private UploadStorage() {
    }

    public static Path directory(String category) throws IOException {
        validateFileName(category);
        Path root = RuntimeSettings.uploadRoot().toFile().getCanonicalFile().toPath();
        Path directory = root.resolve(category).toFile().getCanonicalFile().toPath();
        if (!root.equals(directory.getParent())) {
            throw new IOException("Upload directory escapes SSA_UPLOAD_ROOT: " + category);
        }
        return directory;
    }

    public static Path resolveFile(Path directory, String fileName) throws IOException {
        validateFileName(fileName);
        Path canonicalDirectory = canonicalDirectory(directory);
        Path file = canonicalDirectory.resolve(fileName).toFile().getCanonicalFile().toPath();
        if (!canonicalDirectory.equals(file.getParent())) {
            throw new IOException("Image path escapes its upload directory.");
        }
        return file;
    }

    public static Path createDirectory(Path directory) throws IOException {
        Path canonicalDirectory = canonicalDirectory(directory);
        Files.createDirectories(canonicalDirectory);
        if (!Files.isDirectory(canonicalDirectory, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Upload path is not a directory: " + canonicalDirectory);
        }
        return canonicalDirectory;
    }

    public static void deleteFile(Path directory, String fileName) throws IOException {
        if (fileName == null || fileName.isEmpty() || "noImage.jpg".equals(fileName)) {
            return;
        }
        Path file = resolveFile(directory, fileName);
        if (Files.exists(file, LinkOption.NOFOLLOW_LINKS) && !Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Refusing to delete a non-file image path: " + file);
        }
        Files.deleteIfExists(file);
    }

    public static ResponseEntity<byte[]> readImage(Path directory, String fileName,
            ServletContext context, String bundledDefault) throws IOException {
        if (directory != null) {
            ResponseEntity<byte[]> image = readExternalImage(directory, fileName);
            if (image != null) {
                return image;
            }
            image = readExternalImage(directory, "noImage.jpg");
            if (image != null) {
                return image;
            }
        }

        if (context != null && bundledDefault != null) {
            try (InputStream in = context.getResourceAsStream(bundledDefault)) {
                if (in != null) {
                    return ResponseEntity.ok().contentType(mediaType(bundledDefault)).body(in.readAllBytes());
                }
            }
        }
        return new ResponseEntity<>(HttpStatus.NOT_FOUND);
    }

    static void validateFileName(String fileName) throws IOException {
        if (fileName == null || fileName.isBlank() || ".".equals(fileName) || "..".equals(fileName)
                || fileName.indexOf('/') >= 0 || fileName.indexOf('\\') >= 0
                || fileName.indexOf(':') >= 0 || fileName.indexOf('\0') >= 0) {
            throw new IOException("Image file name must be a single portable file name.");
        }
    }

    private static Path canonicalDirectory(Path directory) throws IOException {
        if (directory == null || Files.isSymbolicLink(directory)) {
            throw new IOException("Invalid upload directory.");
        }
        return directory.toFile().getCanonicalFile().toPath();
    }

    private static ResponseEntity<byte[]> readExternalImage(Path directory, String fileName) {
        try {
            Path file = resolveFile(directory, fileName);
            if (Files.isRegularFile(file) && Files.isReadable(file)) {
                return ResponseEntity.ok().contentType(mediaType(file.getFileName().toString())).body(Files.readAllBytes(file));
            }
        } catch (IOException | IllegalArgumentException | SecurityException ignored) {
            // Missing, inaccessible or unsafe external images use the bundled fallback.
        }
        return null;
    }

    private static MediaType mediaType(String fileName) {
        String lowerName = fileName.toLowerCase(Locale.ROOT);
        if (lowerName.endsWith(".png")) {
            return MediaType.IMAGE_PNG;
        }
        if (lowerName.endsWith(".gif")) {
            return MediaType.IMAGE_GIF;
        }
        if (lowerName.endsWith(".webp")) {
            return MediaType.parseMediaType("image/webp");
        }
        return MediaType.IMAGE_JPEG;
    }
}
