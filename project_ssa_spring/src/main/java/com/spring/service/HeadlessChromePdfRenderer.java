package com.spring.service;

import java.io.IOException;
import java.io.File;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.spring.util.RuntimeSettings;

/** Renders the existing JSP in Chromium; it deliberately owns no report layout. */
public class HeadlessChromePdfRenderer implements PatrolReportPdfRenderer {

    private static final Duration START_TIMEOUT = Duration.ofSeconds(10);
    private static final Duration RENDER_TIMEOUT = Duration.ofSeconds(
            RuntimeSettings.positiveInt("SSA_PDF_RENDER_TIMEOUT_SECONDS", 30));
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public void render(String reportViewUrl, Path destination) throws IOException {
        Path profile = Files.createTempDirectory("ssa-pdf-chrome-");
        Process browser = null;
        try {
            int debugPort = reservePort();
            browser = startBrowser(debugPort, profile);
            String websocketUrl = waitForDebuggerWebSocket(debugPort, browser);
            try (DevToolsClient devTools = new DevToolsClient(websocketUrl, objectMapper)) {
                devTools.command("Page.enable", objectMapper.createObjectNode());
                ObjectNode navigate = objectMapper.createObjectNode();
                navigate.put("url", reportViewUrl);
                JsonNode navigation = devTools.command("Page.navigate", navigate);
                String navigationError = navigation.path("errorText").asText();
                if (!navigationError.isEmpty()) {
                    throw new IOException("Headless browser could not open the internal PatrolReport view: "
                            + navigationError);
                }
                waitForReportReady(devTools);

                ObjectNode printOptions = objectMapper.createObjectNode();
                printOptions.put("printBackground", true);
                printOptions.put("preferCSSPageSize", true);
                printOptions.put("displayHeaderFooter", false);
                JsonNode result = devTools.command("Page.printToPDF", printOptions);
                String base64Pdf = result.path("data").asText();
                if (base64Pdf.isEmpty()) {
                    throw new IOException("Headless browser returned no PDF data.");
                }
                Files.createDirectories(destination.getParent());
                Files.write(destination, Base64.getDecoder().decode(base64Pdf));
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IOException("PDF rendering was interrupted.", ex);
        } finally {
            if (browser != null) {
                browser.destroyForcibly();
            }
            deleteTemporaryProfile(profile);
        }
    }

    private Process startBrowser(int debugPort, Path profile) throws IOException {
        List<String> command = new ArrayList<>();
        command.add(resolveBrowserExecutable().toString());
        command.add("--headless=new");
        command.add("--disable-gpu");
        command.add("--no-first-run");
        command.add("--no-default-browser-check");
        command.add("--remote-allow-origins=*");
        command.add("--remote-debugging-address=127.0.0.1");
        command.add("--remote-debugging-port=" + debugPort);
        command.add("--user-data-dir=" + profile);
        command.add("about:blank");
        return new ProcessBuilder(command).redirectErrorStream(true).start();
    }

    private Path resolveBrowserExecutable() throws IOException {
        return resolveBrowserExecutable(RuntimeSettings.text("SSA_PDF_BROWSER_PATH", ""),
                System.getenv("PATH"), File.separatorChar == '\\');
    }

    static Path resolveBrowserExecutable(String configured, String searchPath, boolean windows) throws IOException {
        if (configured != null && !configured.isBlank()) {
            try {
                Path path = Path.of(configured.trim());
                if (!path.isAbsolute() || !isExecutableFile(path)) {
                    throw new IOException("SSA_PDF_BROWSER_PATH must name an absolute, readable executable file.");
                }
                return path.normalize();
            } catch (InvalidPathException | SecurityException ex) {
                throw new IOException("SSA_PDF_BROWSER_PATH is not a valid accessible executable path.");
            }
        }

        if (windows) {
            for (String candidate : List.of(
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
                "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe")) {
                Path path = Path.of(candidate);
                if (isExecutableFile(path)) {
                    return path;
                }
            }
        }

        List<String> executableNames = windows
                ? List.of("chrome.exe", "msedge.exe", "chromium.exe")
                : List.of("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge");
        if (searchPath != null) {
            for (String entry : searchPath.split(java.util.regex.Pattern.quote(File.pathSeparator))) {
                try {
                    Path directory = Path.of(entry);
                    // Empty or relative PATH entries depend on Tomcat's working directory.
                    if (!directory.isAbsolute()) {
                        continue;
                    }
                    for (String name : executableNames) {
                        Path candidate = directory.resolve(name);
                        if (isExecutableFile(candidate)) {
                            return candidate.normalize();
                        }
                    }
                } catch (InvalidPathException | SecurityException ignored) {
                    // Other PATH entries may still contain a usable browser.
                }
            }
        }
        throw new IOException("Chrome or Edge executable was not found. Configure SSA_PDF_BROWSER_PATH.");
    }

    private static boolean isExecutableFile(Path path) {
        return Files.isRegularFile(path) && Files.isReadable(path) && Files.isExecutable(path);
    }

    private String waitForDebuggerWebSocket(int port, Process browser) throws IOException, InterruptedException {
        HttpClient client = HttpClient.newHttpClient();
        long deadline = System.nanoTime() + START_TIMEOUT.toNanos();
        IOException lastFailure = null;
        while (System.nanoTime() < deadline) {
            if (!browser.isAlive()) {
                String output = new String(browser.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
                throw new IOException("Headless browser exited before its debugging endpoint started: " + output);
            }
            try {
                HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/json/list"))
                        .timeout(Duration.ofSeconds(1)).GET().build();
                JsonNode targets = objectMapper.readTree(client.send(request, HttpResponse.BodyHandlers.ofString()).body());
                if (targets.isArray()) {
                    for (JsonNode target : targets) {
                        if (!"page".equals(target.path("type").asText())) {
                            continue;
                        }
                        String websocket = target.path("webSocketDebuggerUrl").asText();
                        if (!websocket.isEmpty()) {
                            return websocket;
                        }
                    }
                }
            } catch (IOException ex) {
                lastFailure = ex;
            }
            Thread.sleep(50);
        }
        throw new IOException("Headless browser debugging endpoint did not start.", lastFailure);
    }

    private void waitForReportReady(DevToolsClient devTools) throws IOException, InterruptedException {
        long deadline = System.nanoTime() + RENDER_TIMEOUT.toNanos();
        while (System.nanoTime() < deadline) {
            ObjectNode expression = objectMapper.createObjectNode();
            expression.put("expression", "window.__REPORT_RENDER_READY__ === true");
            expression.put("returnByValue", true);
            JsonNode result = devTools.command("Runtime.evaluate", expression);
            if (result.path("result").path("value").asBoolean(false)) {
                return;
            }
            Thread.sleep(50);
        }
        throw new IOException("Timed out while waiting for PatrolReport charts to render. "
                + describeRenderState(devTools));
    }

    private String describeRenderState(DevToolsClient devTools) {
        try {
            ObjectNode expression = objectMapper.createObjectNode();
            expression.put("expression", "JSON.stringify({url: location.href, readyState: document.readyState, "
                    + "renderReady: window.__REPORT_RENDER_READY__, renderError: window.__REPORT_RENDER_ERROR__ || '', "
                    + "chartType: typeof window.Chart, jqueryType: typeof window.jQuery, title: document.title})");
            expression.put("returnByValue", true);
            JsonNode result = devTools.command("Runtime.evaluate", expression);
            return "Render state=" + result.path("result").path("value").asText("unavailable");
        } catch (Exception ex) {
            return "Render state was unavailable.";
        }
    }

    private static int reservePort() throws IOException {
        try (ServerSocket socket = new ServerSocket()) {
            socket.bind(new InetSocketAddress("127.0.0.1", 0));
            return socket.getLocalPort();
        }
    }

    private static void deleteTemporaryProfile(Path profile) {
        try (var paths = Files.walk(profile)) {
            paths.sorted(java.util.Comparator.reverseOrder()).forEach(path -> {
                try { Files.deleteIfExists(path); } catch (IOException ignored) { }
            });
        } catch (IOException ignored) {
            // A browser-locked profile is harmless and contains no report cache.
        }
    }

    private static final class DevToolsClient implements WebSocket.Listener, AutoCloseable {
        private final ObjectMapper mapper;
        private final AtomicInteger nextId = new AtomicInteger();
        private final Map<Integer, CompletableFuture<JsonNode>> responses = new ConcurrentHashMap<>();
        private final StringBuilder incoming = new StringBuilder();
        private final WebSocket socket;

        private DevToolsClient(String endpoint, ObjectMapper mapper) {
            this.mapper = mapper;
            this.socket = HttpClient.newHttpClient().newWebSocketBuilder()
                    .connectTimeout(START_TIMEOUT).buildAsync(URI.create(endpoint), this).join();
        }

        private JsonNode command(String method, ObjectNode params) throws IOException, InterruptedException {
            int id = nextId.incrementAndGet();
            ObjectNode command = mapper.createObjectNode();
            command.put("id", id);
            command.put("method", method);
            command.set("params", params);
            CompletableFuture<JsonNode> response = new CompletableFuture<>();
            responses.put(id, response);
            socket.sendText(command.toString(), true).join();
            try {
                JsonNode node = response.get(RENDER_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS);
                if (node.has("error")) {
                    throw new IOException("Chrome DevTools command failed: " + node.path("error").path("message").asText());
                }
                return node.path("result");
            } catch (java.util.concurrent.TimeoutException ex) {
                throw new IOException("Chrome DevTools command timed out: " + method, ex);
            } catch (java.util.concurrent.ExecutionException ex) {
                throw new IOException("Chrome DevTools command failed: " + method, ex.getCause());
            } finally {
                responses.remove(id);
            }
        }

        @Override
        public CompletionStage<?> onText(WebSocket socket, CharSequence data, boolean last) {
            incoming.append(data);
            if (last) {
                try {
                    JsonNode message = mapper.readTree(incoming.toString());
                    JsonNode id = message.get("id");
                    if (id != null) {
                        CompletableFuture<JsonNode> response = responses.get(id.asInt());
                        if (response != null) response.complete(message);
                    }
                } catch (IOException ignored) {
                    // The matching command will time out and report a safe rendering failure.
                } finally {
                    incoming.setLength(0);
                }
            }
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onOpen(WebSocket socket) { socket.request(1); }

        @Override
        public void close() { socket.sendClose(WebSocket.NORMAL_CLOSURE, "done").join(); }
    }
}
