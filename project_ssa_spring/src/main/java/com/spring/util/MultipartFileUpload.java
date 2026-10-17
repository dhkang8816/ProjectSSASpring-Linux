package com.spring.util;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.Locale;
import java.util.UUID;

import org.springframework.web.multipart.MultipartFile;

import com.spring.exception.EmptyMultipartFileException;

public class MultipartFileUpload {

	private static final String[] ALLOWED_IMAGE_EXTENSIONS = { "jpg", "jpeg", "png" };

	public static String saveFile(String uploadPath, MultipartFile multi)
			throws EmptyMultipartFileException, IllegalStateException, IOException {

		if (multi == null || multi.isEmpty()) {
			throw new EmptyMultipartFileException();
		}
		String originalName = multi.getOriginalFilename();
		UploadStorage.validateFileName(originalName);
		String uuid = UUID.randomUUID().toString().replace("-", "");
		String fileName = uuid + "$$" + originalName;
		Path uploadDirectory = UploadStorage.createDirectory(uploadDirectory(uploadPath));
		transferFile(uploadDirectory, fileName, multi);

		return fileName;
	}

	public static String saveFile(String uploadPath, String oldFile, MultipartFile multi)
			throws EmptyMultipartFileException, IllegalStateException, IOException {
		Path directory = uploadDirectory(uploadPath);
		if (oldFile != null && !oldFile.isEmpty() && !"noImage.jpg".equals(oldFile)) {
			// Validate the old DB value before writing or deleting any image.
			UploadStorage.resolveFile(directory, oldFile);
		}
		String fileName = saveFile(uploadPath, multi);
		try {
			UploadStorage.deleteFile(directory, oldFile);
		} catch (IOException | SecurityException ex) {
			try {
				UploadStorage.deleteFile(directory, fileName);
			} catch (IOException | SecurityException cleanupFailure) {
				ex.addSuppressed(cleanupFailure);
			}
			throw ex;
		}
		
		return fileName;
	}

	/**
	 * Stores an application image with a server-generated name.  This is kept
	 * separate from {@link #saveFile(String, MultipartFile)} so existing member
	 * upload file names remain fully compatible.
	 */
	public static String saveImageFile(String uploadPath, MultipartFile multi)
			throws EmptyMultipartFileException, IllegalStateException, IOException {

		if (multi == null || multi.isEmpty()) {
			throw new EmptyMultipartFileException();
		}

		String originalName = multi.getOriginalFilename();
		String extension = getExtension(originalName);
		if (!isAllowedImageExtension(extension) || !isAllowedImageContentType(multi.getContentType(), extension)) {
			throw new IllegalArgumentException("JPG, JPEG, PNG 이미지 파일만 등록할 수 있습니다.");
		}

		String fileName = UUID.randomUUID().toString().replace("-", "") + "." + extension;
		Path uploadDirectory = UploadStorage.createDirectory(uploadDirectory(uploadPath));
		transferFile(uploadDirectory, fileName, multi);
		return fileName;
	}

	private static void transferFile(Path directory, String fileName, MultipartFile multi) throws IOException {
		Path destination = UploadStorage.resolveFile(directory, fileName);
		if (Files.exists(destination, LinkOption.NOFOLLOW_LINKS)) {
			throw new IOException("Generated upload destination already exists.");
		}
		try {
			multi.transferTo(destination.toFile());
		} catch (IOException | RuntimeException ex) {
			try {
				Files.deleteIfExists(destination);
			} catch (IOException | RuntimeException cleanupFailure) {
				ex.addSuppressed(cleanupFailure);
			}
			throw ex;
		}
	}

	private static Path uploadDirectory(String uploadPath) throws IOException {
		if (uploadPath == null || uploadPath.isBlank()) {
			throw new IOException("Upload directory is required.");
		}
		try {
			return Path.of(uploadPath);
		} catch (InvalidPathException ex) {
			throw new IOException("Invalid upload directory.", ex);
		}
	}

	private static String getExtension(String originalName) {
		if (originalName == null) {
			return "";
		}
		int lastDot = originalName.lastIndexOf('.');
		if (lastDot < 0 || lastDot == originalName.length() - 1) {
			return "";
		}
		return originalName.substring(lastDot + 1).toLowerCase(Locale.ROOT);
	}

	private static boolean isAllowedImageExtension(String extension) {
		for (String allowedExtension : ALLOWED_IMAGE_EXTENSIONS) {
			if (allowedExtension.equals(extension)) {
				return true;
			}
		}
		return false;
	}

	private static boolean isAllowedImageContentType(String contentType, String extension) {
		if (contentType == null) {
			return false;
		}

		String normalizedContentType = contentType.toLowerCase(Locale.ROOT);
		boolean jpeg = "jpg".equals(extension) || "jpeg".equals(extension);
		return (jpeg && ("image/jpeg".equals(normalizedContentType) || "image/jpg".equals(normalizedContentType)))
				|| ("png".equals(extension) && "image/png".equals(normalizedContentType));
	}
}
