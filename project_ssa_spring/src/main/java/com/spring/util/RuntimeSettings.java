package com.spring.util;

import java.io.File;
import java.net.URI;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;


public final class RuntimeSettings {

    private RuntimeSettings() {
    }

    public static String text(String name, String defaultValue) {
        String value = System.getProperty(name);
        if (value == null || value.trim().isEmpty()) {
            value = System.getenv(name);
        }
        return (value == null || value.trim().isEmpty()) ? defaultValue : value.trim();
    }

    public static Path uploadRoot() {
        String defaultPath = File.separatorChar == '\\' ? "C:\\upload" : "/var/lib/project-ssa/uploads";
        return absolutePath("SSA_UPLOAD_ROOT", defaultPath);
    }

    public static Path cacheRoot() {
        String configured = text("SSA_CACHE_ROOT", "");
        String defaultPath = File.separatorChar == '\\' && configured.isBlank()
                ? uploadRoot().toString() : "/var/cache/project-ssa";
        return absolutePath("SSA_CACHE_ROOT", defaultPath);
    }

    private static Path absolutePath(String name, String defaultPath) {
        String configuredPath = text(name, defaultPath);
        try {
            Path path = Path.of(configuredPath);
            if (!path.isAbsolute()) {
                throw new IllegalStateException(name + " must be an absolute path for the current operating system.");
            }
            return path.normalize();
        } catch (InvalidPathException ex) {
            throw new IllegalStateException(name + " is not a valid path.");
        }
    }

    public static int positiveInt(String name, int defaultValue) {
        try {
            int value = Integer.parseInt(text(name, String.valueOf(defaultValue)));
            return value > 0 ? value : defaultValue;
        } catch (NumberFormatException ignored) {
            return defaultValue;
        }
    }

    public static boolean enabled(String name, boolean defaultValue) {
        String value = text(name, String.valueOf(defaultValue));
        if ("true".equalsIgnoreCase(value)) {
            return true;
        }
        if ("false".equalsIgnoreCase(value)) {
            return false;
        }
        return defaultValue;
    }
    
    public static String kakaoRestApiKey() {
        return text("KAKAO_REST_API_KEY", "");
    }

    public static String discordInviteUrl() {
        String configuredUrl = text("SSA_DISCORD_INVITE_URL", "");
        try {
            URI uri = URI.create(configuredUrl);
            String host = uri.getHost();
            boolean isDiscordHost = "discord.gg".equalsIgnoreCase(host)
                    || "www.discord.gg".equalsIgnoreCase(host)
                    || "discord.com".equalsIgnoreCase(host)
                    || "www.discord.com".equalsIgnoreCase(host);
            if ("https".equalsIgnoreCase(uri.getScheme()) && isDiscordHost) {
                return uri.toString();
            }
        } catch (IllegalArgumentException ignored) {
            // A malformed deployment setting must not render an unsafe sidebar link.
        }
        return configuredUrl;
    }
}
