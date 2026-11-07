package cqa;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import com.sun.net.httpserver.*;
import cqa.dataset.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.test.system.*;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import java.io.IOException;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@ExtendWith(OutputCaptureExtension.class)
class OrganizerApiTest {
    @TempDir static Path directory;
    private final ObjectMapper json = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    private final AtomicReference<String> mode = new AtomicReference<>("ok");
    private final AtomicInteger requests = new AtomicInteger(), redirects = new AtomicInteger();
    private volatile String query, method;
    private HttpServer upstream;
    private ExecutorService workers;
    private ServletWebServerApplicationContext app;
    private String configured, base, group;
    private int sequence;
    private static final String RAW_QUERY = "api-version=synthetic&sp=%2fpath%2Fraw&sig=SYNTHETIC_SIGNATURE%2B%2f%3D+plus&sv=1&extra=&extra=two&&group_id=OLD";

    private ServletWebServerApplicationContext boot(String url, String database) {
        // Synthetic URL only; real credentials must never be passed as process arguments.
        return (ServletWebServerApplicationContext) new SpringApplicationBuilder(Application.class).run(
            "--server.port=0", "--cqa.db-path=" + directory.resolve(database), "--cqa.organizer-url=" + url,
            "--cqa.organizer-connect-timeout-ms=500", "--cqa.organizer-response-timeout-ms=2000",
            "--spring.main.banner-mode=off", "--logging.level.root=WARN");
    }
    private String url(ServletWebServerApplicationContext context) { return "http://127.0.0.1:" + context.getWebServer().getPort(); }
    @BeforeAll void start() throws Exception {
        upstream = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        workers = Executors.newCachedThreadPool(); upstream.setExecutor(workers);
        upstream.createContext("/signed", this::respond);
        upstream.createContext("/redirect-target", exchange -> { redirects.incrementAndGet(); exchange.sendResponseHeaders(204, -1); exchange.close(); });
        upstream.start();
        configured = "http://127.0.0.1:" + upstream.getAddress().getPort() + "/signed?" + RAW_QUERY;
        app = boot(configured, "fetch.sqlite"); base = url(app);
    }
    @AfterAll void stop() { if (app != null) app.close(); upstream.stop(0); workers.shutdownNow(); http.close(); }
    @BeforeEach void fresh() { mode.set("ok"); group = "SYNTHETIC-" + ++sequence; requests.set(0); redirects.set(0); }
    private static String decode(String s) { return URLDecoder.decode(s, StandardCharsets.UTF_8); }
    private String requested(String raw) {
        return Arrays.stream(raw.split("&")).map(p -> p.split("=", 2))
            .filter(p -> decode(p[0]).equals("group_id")).map(p -> decode(p[1])).findFirst().orElseThrow();
    }
    private ObjectNode dataset(String selected) {
        ObjectNode root = json.createObjectNode().put("isSuccess", true).put("error", "");
        ObjectNode data = root.putObject("data").put("dataset_group_id", selected).put("total_records", 3);
        ArrayNode records = data.putArray("records");
        for (String language : List.of("RU", "KZ", "EN")) {
            ObjectNode record = records.addObject().put("conversation_id", language).put("language", language)
                .put("channel", language.equals("RU") ? "voice call" : "agent chat")
                .put("audio_url", "https://example.invalid/synthetic.wav?sig=SYNTHETIC_AUDIO");
            ArrayNode turns = record.putArray("transcript");
            for (String role : List.of("client", "bot", "operator", "system", "operator"))
                turns.addObject().put("timestamp", language.equals("RU") ? "2026-11-07T10:00:00+05:00" : "00:01")
                    .put("speaker", role).put("text", " Synthetic Қ / Привет / e\u0301 / 😀 " + language);
        }
        return root;
    }
    private void respond(HttpExchange exchange) throws IOException {
        requests.incrementAndGet(); query = exchange.getRequestURI().getRawQuery(); method = exchange.getRequestMethod();
        String current = mode.get();
        try {
            if (current.equals("slow_headers")) Thread.sleep(2600);
            if (current.startsWith("status-")) {
                int status = Integer.parseInt(current.substring(7));
                exchange.getResponseHeaders().set("Location", "/redirect-target?sig=SYNTHETIC_SIGNATURE");
                byte[] error = "SYNTHETIC_SIGNATURE https://example.invalid/private SYNTHETIC_TRANSCRIPT".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(status, error.length); exchange.getResponseBody().write(error); return;
            }
            if (current.equals("oversized_header")) { exchange.sendResponseHeaders(200, 16*1024*1024+1); return; }
            if (current.equals("oversized_chunked")) {
                exchange.sendResponseHeaders(200, 0);
                byte[] chunk = new byte[64*1024]; Arrays.fill(chunk, (byte)' ');
                for (int i = 0; i < 257; i++) exchange.getResponseBody().write(chunk);
                return;
            }
            var body = dataset(requested(query));
            var data = (ObjectNode)body.get("data"); var record = (ObjectNode)body.at("/data/records/2");
            switch (current) {
                case "mismatch" -> data.put("dataset_group_id", "OTHER_GROUP");
                case "failed" -> body.put("isSuccess", false);
                case "error" -> body.put("error", "SYNTHETIC_TRANSCRIPT");
                case "no_data" -> body.remove("data");
                case "bad_count" -> data.put("total_records", 4);
                case "count_string" -> data.put("total_records", "3");
                case "bad_role" -> ((ObjectNode)record.at("/transcript/1")).put("speaker", "unknown");
                case "bad_language" -> record.put("language", "FR");
                case "bad_channel" -> record.put("channel", "unknown");
                case "bad_message" -> ((ObjectNode)record.at("/transcript/0")).put("text", 42);
                case "no_messages" -> record.putArray("transcript");
                case "extra" -> record.put("token", "SYNTHETIC_SIGNATURE");
                case "duplicate_records" -> record.put("conversation_id", "RU");
                case "optional" -> { body.remove("error"); for (var row : data.get("records")) ((ObjectNode)row).remove("audio_url"); }
                case "conflict" -> {
                    ((ObjectNode)data.get("records").get(0)).put("conversation_id", "NEW");
                    ((ObjectNode)record.at("/transcript/0")).put("text", "SYNTHETIC_TRANSCRIPT changed content");
                }
            }
            byte[] bytes = json.writeValueAsBytes(body);
            if (current.equals("invalid_json")) bytes = "{bad SYNTHETIC_SIGNATURE".getBytes(StandardCharsets.UTF_8);
            if (current.equals("duplicate_key")) bytes = "{\"isSuccess\":true,\"isSuccess\":false}".getBytes(StandardCharsets.UTF_8);
            if (current.equals("invalid_utf8")) bytes = new byte[]{(byte)0xc3, (byte)0x28};
            if (current.equals("trailing")) bytes = (body + " {}").getBytes(StandardCharsets.UTF_8);
            if (current.equals("gzip")) exchange.getResponseHeaders().set("Content-Encoding", "gzip");
            exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
            exchange.sendResponseHeaders(200, current.equals("slow_body") ? 0 : bytes.length);
            if (current.equals("slow_body")) { exchange.getResponseBody().write('{'); exchange.getResponseBody().flush(); Thread.sleep(2600); }
            exchange.getResponseBody().write(bytes);
        } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        catch (IOException ignored) { /* Client cancelled a bounded/timeout/redirect response. */ }
        finally { exchange.close(); }
    }
    record Reply(int status, JsonNode body, String raw) {}
    private Reply call(String host, String method, String path, Object body) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create(host + path)).timeout(Duration.ofSeconds(15));
        if (body != null) builder.header("Content-Type", "application/json");
        var response = http.send(builder.method(method, body == null ? HttpRequest.BodyPublishers.noBody()
            : HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build(), HttpResponse.BodyHandlers.ofString());
        return new Reply(response.statusCode(), response.headers().firstValue("content-type").orElse("").contains("json")
            ? json.readTree(response.body()) : NullNode.instance, response.body());
    }
    private Reply fetch() throws Exception { return call(base, "POST", "/api/datasets/fetch", Map.of("group_id", group)); }
    private JsonNode conversations() throws Exception { var reply = call(base, "GET", "/api/conversations", null); assertEquals(200, reply.status()); return reply.body(); }
    private void safe(String text) {
        for (String secret : List.of("SYNTHETIC_SIGNATURE", "SYNTHETIC_AUDIO", "SYNTHETIC_TRANSCRIPT", "example.invalid", configured, "SQLException", directory.toString())) assertFalse(text.contains(secret), "Sensitive value exposed");
    }
    private void error(Reply reply, int status, String code) {
        assertEquals(status, reply.status(), reply.raw()); assertEquals(code, reply.body().at("/detail/code").asText());
        assertFalse(reply.body().at("/detail/retryable").asBoolean()); safe(reply.raw());
    }
    @Test void getPreservesRawQueryAndImportsAllSourceFieldsExactly() throws Exception {
        assertEquals(200, fetch().status()); assertEquals("GET", method);
        assertEquals(RAW_QUERY.replace("group_id=OLD", "group_id=" + group), query); assertEquals(1, requests.get());
        for (JsonNode record : dataset(group).at("/data/records")) {
            var response = call(base, "GET", "/api/conversations/" + group + ":" + record.get("conversation_id").asText(), null);
            assertEquals(200, response.status()); var saved = response.body();
            for (String field : List.of("language", "channel", "transcript", "audio_url")) assertEquals(record.get(field), saved.get(field));
            for (int i = 0; i < 5; i++) {
                ObjectNode turn = record.get("transcript").get(i).deepCopy(); turn.put("id", "m000" + (i+1));
                assertEquals(turn, saved.get("messages").get(i));
            }
        }
    }
    @Test void repeatAndUploadShareIdempotencyWhileGroupsStayIndependent() throws Exception {
        group = "DEV"; assertEquals(3, fetch().body().get("imported_records").asInt()); var after = conversations();
        assertEquals(200, fetch().status()); assertEquals(after, conversations());
        assertEquals(200, call(base, "POST", "/api/datasets/import", dataset("DEV")).status()); assertEquals(after, conversations());
        group = "CONTROL"; assertEquals(200, fetch().status()); assertEquals(after.size()+3, conversations().size());
        assertEquals(3, app.getBean(JdbcTemplate.class).queryForObject("SELECT count(*) FROM conversations WHERE dataset_group_id='DEV'", Integer.class));
        assertEquals(3, app.getBean(JdbcTemplate.class).queryForObject("SELECT count(*) FROM conversations WHERE dataset_group_id='CONTROL'", Integer.class));
    }
    @Test void groupCharactersCannotInjectSignatureOrOtherParameters() throws Exception {
        group = "CONTROL +&sig=NEW?#Қ"; assertEquals(200, fetch().status());
        assertEquals(group, requested(query));
        assertEquals(RAW_QUERY.replace("group_id=OLD", "group_id=" + URLEncoder.encode(group, StandardCharsets.UTF_8).replace("+", "%20")), query);
    }
    @Test void conflictingLaterRecordRollsBackEarlierNewRecord() throws Exception {
        assertEquals(200, fetch().status()); var before = conversations(); mode.set("conflict");
        error(fetch(), 409, "VERSION_CONFLICT"); assertEquals(before, conversations());
        assertEquals(404, call(base, "GET", "/api/conversations/" + group + ":NEW", null).status());
    }
    @ParameterizedTest @ValueSource(strings={"failed","error","no_data","bad_count","count_string","bad_role","bad_language","bad_channel","bad_message","no_messages","extra","duplicate_records","invalid_json","duplicate_key","invalid_utf8","trailing","gzip"})
    void malformedUpstreamNeverWritesOrLeaks(String behavior, CapturedOutput output) throws Exception {
        var before = conversations(); mode.set(behavior); error(fetch(), 502, "ORGANIZER_INVALID_RESPONSE");
        assertEquals(before, conversations()); assertEquals(1, requests.get()); safe(output.getAll());
    }
    @Test void mismatchedGroupIsNotImported() throws Exception {
        var before = conversations(); mode.set("mismatch"); error(fetch(), 502, "ORGANIZER_GROUP_MISMATCH"); assertEquals(before, conversations());
    }
    @ParameterizedTest @ValueSource(ints={401,403,404,429,500,503,302,307})
    void upstreamErrorsAreMappedWithoutBodiesOrRedirects(int status, CapturedOutput output) throws Exception {
        mode.set("status-" + status); var before = conversations();
        String code = switch(status) { case 401,403 -> "ACCESS_DENIED"; case 404 -> "NOT_FOUND"; case 429 -> "RATE_LIMITED"; case 302,307 -> "REDIRECT_REJECTED"; default -> "UPSTREAM_ERROR"; };
        error(fetch(), status == 404 ? 404 : status == 429 ? 503 : 502, "ORGANIZER_" + code);
        assertEquals(before, conversations()); assertEquals(1, requests.get()); assertEquals(0, redirects.get()); safe(output.getAll());
    }
    @ParameterizedTest @ValueSource(strings={"slow_headers","slow_body"})
    void deadlineCoversHeadersAndEntireBody(String behavior) throws Exception {
        mode.set(behavior); var before = conversations(); long start = System.nanoTime();
        error(fetch(), 504, "ORGANIZER_TIMEOUT"); assertTrue(Duration.ofNanos(System.nanoTime()-start).toMillis() < 5000);
        assertEquals(before, conversations()); assertEquals(1, requests.get());
    }
    @ParameterizedTest @ValueSource(strings={"oversized_header","oversized_chunked"})
    void boundsResponseWithoutTrustingContentLength(String behavior) throws Exception {
        mode.set(behavior); var before = conversations(); error(fetch(), 502, "ORGANIZER_RESPONSE_TOO_LARGE"); assertEquals(before, conversations());
    }
    @Test void uploadAndFetchUseIdenticalOptionalDefaults() throws Exception {
        mode.set("optional"); assertEquals(200, fetch().status());
        var dataset = dataset(group); dataset.remove("error"); for (var record : dataset.at("/data/records")) ((ObjectNode)record).remove("audio_url");
        assertEquals(200, call(base, "POST", "/api/datasets/import", dataset).status());
        assertTrue(call(base, "GET", "/api/conversations/" + group + ":RU", null).body().get("audio_url").isNull());
    }
    @ParameterizedTest @ValueSource(strings={"blank","missing","number","extra_url","null","long"})
    void invalidBrowserInputCannotChooseDestination(String invalid) throws Exception {
        var body = json.createObjectNode().put("group_id", group);
        switch(invalid) {
            case "blank" -> body.put("group_id", " \u00a0\t"); case "missing" -> body.remove("group_id");
            case "number" -> body.put("group_id", 42); case "null" -> body.putNull("group_id");
            case "long" -> body.put("group_id", "x".repeat(201)); case "extra_url" -> body.put("url", "https://example.invalid/private");
        }
        error(call(base, "POST", "/api/datasets/fetch", body), 422, "INVALID_INPUT"); assertEquals(0, requests.get());
    }
    @Test void missingConfigurationStartsAndManualUploadStillWorks() throws Exception {
        try (var unconfigured = boot("", "unconfigured.sqlite")) {
            String target = url(unconfigured);
            assertEquals(200, call(target, "GET", "/api/health", null).status());
            error(call(target, "POST", "/api/datasets/fetch", Map.of("group_id", group)), 503, "ORGANIZER_UNCONFIGURED");
            assertEquals(200, call(target, "POST", "/api/datasets/import", dataset(group)).status()); assertEquals(0, requests.get());
        }
    }
    @Test void refusedConnectionAndInvalidConfigurationHaveSafeErrors() throws Exception {
        int port; try (var socket = new java.net.ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"))) { port = socket.getLocalPort(); }
        try (var refused = boot("http://127.0.0.1:" + port + "/?sig=SYNTHETIC_SIGNATURE", "refused.sqlite")) {
            error(call(url(refused), "POST", "/api/datasets/fetch", Map.of("group_id", group)), 503, "ORGANIZER_UNAVAILABLE");
        }
        try (var invalid = boot("https://user:SYNTHETIC_SIGNATURE@example.invalid/private#fragment", "invalid.sqlite")) {
            error(call(url(invalid), "POST", "/api/datasets/fetch", Map.of("group_id", group)), 503, "ORGANIZER_CONFIGURATION_ERROR");
            assertEquals(200, call(url(invalid), "GET", "/api/health", null).status());
        }
    }
    @Test void restartRetainsExactSourcesAndFetchIsStillIdempotent() throws Exception {
        assertEquals(200, fetch().status()); var before = app.getBean(JdbcTemplate.class).queryForList("SELECT * FROM conversations ORDER BY id");
        app.close(); app = boot(configured, "fetch.sqlite"); base = url(app);
        assertEquals(before, app.getBean(JdbcTemplate.class).queryForList("SELECT * FROM conversations ORDER BY id"));
        assertEquals(200, fetch().status()); assertEquals(before, app.getBean(JdbcTemplate.class).queryForList("SELECT * FROM conversations ORDER BY id"));
    }
    @Test void frontendContainsFormButNoUpstreamUrlOrSecret() throws Exception {
        var html = call(base, "GET", "/", null).raw(); var js = call(base, "GET", "/js/datasets.js", null).raw();
        assertTrue(html.contains("id=\"group-id\"")); assertTrue(html.contains("Fetch dataset"));
        assertTrue(js.contains("textContent")); assertFalse(js.contains("innerHTML")); assertTrue(js.contains("'/api/datasets/fetch'"));
        safe(html); safe(js);
    }
}
