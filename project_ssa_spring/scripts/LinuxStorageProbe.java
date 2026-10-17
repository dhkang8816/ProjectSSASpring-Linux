import java.io.*;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.sql.*;
import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.spring.util.MultipartFileUpload;
import com.spring.util.UploadStorage;
import org.springframework.web.multipart.MultipartFile;

/** Service-account probe: SELECT only; removes only its own disposable upload. */
class LinuxStorageProbe {
    static final Map<String, Object> result = new LinkedHashMap<>();
    static Path upload;

    public static void main(String[] args) throws Exception {
        upload = Path.of(System.getenv().getOrDefault("SSA_UPLOAD_ROOT", "/var/lib/project-ssa/uploads"));
        if (Arrays.asList(args).contains("--oracle")) oracle();
        if (Arrays.asList(args).contains("--upload")) upload();
        System.out.println("SSA_STORAGE_PROBE=" + new ObjectMapper().writeValueAsString(result));
    }

    static void oracle() {
        Map<String, Object> checks = new LinkedHashMap<>();
        result.put("oracle", checks);
        Properties settings = new Properties();
        try (InputStream input = LinuxStorageProbe.class.getClassLoader()
                .getResourceAsStream("com/spring/properties/jdbc.properties")) {
            if (input == null) throw new IOException("JDBC resource unavailable");
            settings.load(input);
            Class.forName(settings.getProperty("jdbc.driverClassName"));
            DriverManager.setLoginTimeout(5);
            try (Connection connection = DriverManager.getConnection(settings.getProperty("jdbc.url"),
                    settings.getProperty("jdbc.username"), settings.getProperty("jdbc.password"))) {
                connection.setAutoCommit(false);
                try (Statement statement = connection.createStatement()) {
                    statement.setQueryTimeout(10);
                    statement.execute("SET TRANSACTION READ ONLY");
                    try (ResultSet rows = statement.executeQuery("SELECT 1 FROM DUAL")) {
                        checks.put("select1", rows.next() && rows.getInt(1) == 1);
                    }
                    String[][] references = {{"MEMBER", "PICTURE", "member"},
                            {"ANIMAL_DETAIL", "ANIMAL_PICTURE", "animals"},
                            {"DETECTION_LOG", "SNAPSHOT_PATH", "detection"},
                            {"DANGER_LOG", "DSNAPSHOT_PATH", "dangerlog"}};
                    for (String[] reference : references) {
                        Map<String, Object> counts = new LinkedHashMap<>();
                        long total = 0, defaults = 0, existing = 0, missing = 0, invalid = 0;
                        try (ResultSet rows = statement.executeQuery("SELECT " + reference[1] + " FROM " + reference[0])) {
                            while (rows.next()) {
                                total++;
                                String name = rows.getString(1);
                                if (name == null || name.isBlank() || name.equals("noImage.jpg")) { defaults++; continue; }
                                if (name.contains("/") || name.contains("\\") || name.contains(":") || name.equals("..")) { invalid++; continue; }
                                Path root = upload.resolve(reference[2]);
                                Path image = root.resolve(name);
                                if (Files.isRegularFile(image) && Files.isReadable(image)
                                        && image.toRealPath().getParent().equals(root.toRealPath())) existing++;
                                else missing++;
                            }
                            counts.put("rows", total); counts.put("defaults", defaults);
                            counts.put("existing", existing); counts.put("missing_or_unreadable", missing);
                            counts.put("invalid_reference", invalid);
                        } catch (SQLException error) { counts.put("oracle_error_code", error.getErrorCode()); }
                        checks.put(reference[0], counts);
                    }
                } finally { connection.rollback(); }
            }
        } catch (SQLException error) {
            checks.put("error_type", error.getClass().getSimpleName());
            checks.put("oracle_error_code", error.getErrorCode());
        } catch (Exception error) { checks.put("error_type", error.getClass().getSimpleName()); }
    }

    static void upload() {
        Map<String, Object> checks = new LinkedHashMap<>();
        result.put("member_storage_helper", checks);
        String name = null;
        Path directory = null;
        try {
            directory = UploadStorage.directory("member");
            if (!Files.isDirectory(directory)) throw new IOException("Member directory is not prepared");
            byte[] data = Base64.getDecoder().decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP7sAAAAASUVORK5CYII=");
            MultipartFile image = new MultipartFile() {
                public String getName() { return "pictureFile"; }
                public String getOriginalFilename() { return "ssa-permission-probe.png"; }
                public String getContentType() { return "image/png"; }
                public boolean isEmpty() { return false; }
                public long getSize() { return data.length; }
                public byte[] getBytes() { return data; }
                public InputStream getInputStream() { return new ByteArrayInputStream(data); }
                public void transferTo(File destination) throws IOException { Files.write(destination.toPath(), data); }
            };
            name = MultipartFileUpload.saveImageFile(directory.toString(), image);
            var response = UploadStorage.readImage(directory, name, null, null);
            checks.put("readback", response.getStatusCode().value() == 200 && Arrays.equals(data, response.getBody()));
            Path file = directory.resolve(name);
            checks.put("permissions", PosixFilePermissions.toString(Files.getPosixFilePermissions(file)));
            checks.put("group", Files.readAttributes(file, "posix:group").get("group").toString());
        } catch (Exception error) { checks.put("error_type", error.getClass().getSimpleName()); }
        finally {
            if (name != null && directory != null) {
                try { Files.delete(directory.resolve(name)); checks.put("probe_removed", true); }
                catch (Exception error) { checks.put("cleanup_error", error.getClass().getSimpleName()); }
            }
        }
    }
}
