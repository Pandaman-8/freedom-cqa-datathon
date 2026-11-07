package cqa;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

/** T14 workflow on actual model-origin rows, created through Java + fake ML HTTP.
 * These tests establish persistence/review behavior, not live model judgment quality. */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ModelReviewApiTest {
    @TempDir static Path directory;
    private final ObjectMapper json = new ObjectMapper();
    private final HttpClient client = HttpClient.newHttpClient();
    private final AtomicInteger calls = new AtomicInteger();
    private HttpServer fake;
    private ServletWebServerApplicationContext app;
    private ObjectNode fixture, expected, request;
    private JsonNode original;
    private String base, id;
    private Map<String, Object> originalRow, ledgerRow;

    private JdbcTemplate db() { return app.getBean(JdbcTemplate.class); }
    private void boot() {
        app = (ServletWebServerApplicationContext) new SpringApplicationBuilder(Application.class).run(
            "--server.port=0", "--cqa.db-path=" + directory.resolve("model-review.sqlite"),
            "--cqa.ml-url=http://127.0.0.1:" + fake.getAddress().getPort() + "/v1/evaluate",
            "--cqa.organizer-url=", "--spring.main.banner-mode=off", "--logging.level.root=WARN");
        base = "http://127.0.0.1:" + app.getWebServer().getPort();
    }
    @BeforeAll void start() throws Exception {
        Path source = Path.of("../ml-service/tests/fixtures/en_public_na");
        fixture = (ObjectNode) json.readTree(source.resolve("request.json").toFile());
        expected = (ObjectNode) json.readTree(source.resolve("expected.json").toFile());
        fake = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        fake.createContext("/v1/evaluate", exchange -> {
            try (exchange) {
                calls.incrementAndGet();
                var input = json.readTree(exchange.getRequestBody());
                assertEquals("POST", exchange.getRequestMethod());
                assertEquals(fixture.get("conversation"), input.get("conversation"));
                assertEquals(fixture.get("checklist"), input.get("checklist"));
                var result = json.createObjectNode().put("contract_version", "2.0.0")
                    .put("request_id", input.get("request_id").asText())
                    .put("conversation_id", input.at("/conversation/id").asText())
                    .put("checklist_key", "synthetic-local").put("checklist_version", 1);
                result.set("answers", expected.get("answers"));
                result.putObject("diagnostics").put("provider", "local-test").put("model", "fake-http")
                    .put("prompt_version", "synthetic-test").put("attempt_count", 1)
                    .putNull("input_tokens").putNull("output_tokens").putNull("estimated_cost_usd")
                    .put("latency_ms", 1).putArray("warnings");
                byte[] bytes = json.writeValueAsBytes(result);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        fake.start(); boot();
        var conversation = fixture.get("conversation");
        var dataset = json.createObjectNode().put("isSuccess", true);
        var data = dataset.putObject("data").put("dataset_group_id", "SYNTHETIC").put("total_records", 1);
        var record = data.putArray("records").addObject().put("conversation_id", "en_public_na")
            .put("channel", "agent chat").put("language", "EN");
        var turns = record.putArray("transcript");
        for (var message : conversation.get("messages")) {
            var turn = (ObjectNode) message.deepCopy(); turn.remove("id"); turns.add(turn);
        }
        ok("POST", "/api/datasets/import", dataset, 200);
        ok("POST", "/api/checklists/synthetic-local", draft(), 200);
    }
    @AfterAll void stop() { if (app != null) app.close(); if (fake != null) fake.stop(0); client.close(); }
    @BeforeEach void modelEvaluation() throws Exception {
        calls.set(0);
        request = json.createObjectNode().put("request_id", UUID.randomUUID().toString())
            .put("conversation_id", "SYNTHETIC:en_public_na").put("checklist_key", "synthetic-local").put("checklist_version", 1);
        original = ok("POST", "/api/evaluations/auto", request, 200);
        id = original.get("id").asText();
        assertEquals("model", original.get("origin").asText());
        assertEquals(100, original.at("/original_score/overall_score").asInt());
        assertEquals(0, original.get("review_revision").asLong());
        originalRow = db().queryForMap("SELECT * FROM evaluations WHERE id=?", id);
        ledgerRow = db().queryForMap("SELECT * FROM evaluation_requests WHERE request_id=?", request.get("request_id").asText());
    }
    record Reply(int status, JsonNode body) {}
    private Reply call(String method, String route, Object body) throws Exception {
        var req = HttpRequest.newBuilder(URI.create(base + route)).timeout(Duration.ofSeconds(15))
            .header("Content-Type", "application/json").method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build();
        var reply = client.send(req, HttpResponse.BodyHandlers.ofString());
        return new Reply(reply.statusCode(), json.readTree(reply.body()));
    }
    private JsonNode ok(String method, String route, Object body, int code) throws Exception {
        var reply = call(method, route, body); assertEquals(code, reply.status(), reply.body().toString()); return reply.body();
    }
    private JsonNode get() throws Exception { return ok("GET", "/api/evaluations/" + id, null, 200); }
    private JsonNode appeal(String criterion) throws Exception {
        return ok("POST", "/api/evaluations/" + id + "/appeals", Map.of("criterion_id", criterion, "comment", "Synthetic workflow appeal"), 201);
    }
    private ObjectNode answer(String criterion, String kind, Integer value) {
        var answer = json.createObjectNode().put("criterion_id", criterion).put("answer", kind).putNull("value")
            .put("explanation", "Synthetic workflow replacement; not a semantic quality label.");
        if (value != null) answer.put("value", value);
        answer.putArray("evidence").addObject().put("message_id", "m0002").put("quote", "Hello, I am Ada. Support opens at 09:00.");
        return answer;
    }
    private ObjectNode resolution(JsonNode replacement) {
        var body = json.createObjectNode().put("decision", replacement == null ? "confirm" : "change")
            .put("reason", "Synthetic reviewer reason; exercising persisted decisions.");
        body.set("replacement", replacement == null ? NullNode.instance : replacement); return body;
    }
    private String route(JsonNode appeal, long revision) { return "/api/appeals/" + appeal.get("id").asText() + "/resolve?expected_revision=" + revision; }
    private JsonNode resolve(JsonNode appeal, JsonNode replacement) throws Exception {
        return ok("POST", route(appeal, get().get("review_revision").asLong()), resolution(replacement), 200);
    }
    private ObjectNode draft() {
        var draft = (ObjectNode) fixture.get("checklist").deepCopy(); draft.remove(List.of("key", "version")); return draft;
    }
    private void immutable(JsonNode view) {
        for (String field : List.of("original_answers", "original_score", "origin", "checklist_key", "checklist_version", "contract_version", "scoring_version", "created_at"))
            assertEquals(original.get(field), view.get(field), field);
        assertEquals(originalRow, db().queryForMap("SELECT * FROM evaluations WHERE id=?", id));
        assertEquals(ledgerRow, db().queryForMap("SELECT * FROM evaluation_requests WHERE request_id=?", request.get("request_id").asText()));
        assertEquals(1, calls.get(), "Review, replay, restart and versioning must never call ML");
    }

    @Test void changeConfirmCriticalReappealAndRestartPreserveOriginalAndDecisionHistory() throws Exception {
        var clarity = appeal("LOCAL_CLARITY");
        var changed = resolve(clarity, answer("LOCAL_CLARITY", "scale", 4));
        assertEquals(60, changed.at("/final_score/overall_score").asInt());
        assertEquals(75, changed.at("/final_score/applicable_weight").asInt()); // N/A stays excluded.
        assertEquals(2, changed.get("review_revision").asInt());
        var confirm = resolve(appeal("LOCAL_CLARITY"), null);
        assertEquals(changed.get("final_answers"), confirm.get("final_answers"));
        var flagged = resolve(appeal("LOCAL_GROSS"), answer("LOCAL_GROSS", "yes", null));
        assertEquals(60, flagged.at("/final_score/overall_score").asInt());
        assertTrue(flagged.at("/final_score/critical_violation").asBoolean());
        assertEquals(List.of("LOCAL_GROSS"), json.convertValue(flagged.at("/final_score/critical_criterion_ids"), List.class));
        assertFalse(flagged.at("/original_score/critical_violation").asBoolean());
        var finalView = resolve(appeal("LOCAL_GROSS"), answer("LOCAL_GROSS", "no", null));
        assertFalse(finalView.at("/final_score/critical_violation").asBoolean());
        assertEquals(60, finalView.at("/final_score/overall_score").asInt());
        assertEquals("reviewed", finalView.get("review_status").asText());
        assertEquals(8, finalView.get("review_revision").asLong());
        assertEquals(4, finalView.get("appeals").size());
        for (int i = 0; i < 4; i++) {
            var history = finalView.get("appeals").get(i);
            assertEquals(i * 2 + 1, history.get("created_revision").asLong());
            assertEquals(i * 2 + 2, history.get("resolved_revision").asLong());
            assertFalse(history.get("reason").asText().isBlank());
            assertFalse(history.get("resolved_at").isNull());
        }
        assertEquals("confirm", finalView.at("/appeals/1/decision").asText());
        assertTrue(finalView.at("/appeals/1/replacement").isNull());
        assertEquals("yes", finalView.at("/appeals/2/replacement/answer").asText());
        immutable(finalView);
        app.close(); boot();
        assertEquals(finalView, get());
        assertEquals(finalView, ok("POST", "/api/evaluations/auto", request, 200));
        assertEquals("succeeded", ok("GET", "/api/evaluation-requests/" + request.get("request_id").asText(), null, 200).get("status").asText());
        immutable(get());
    }

    @ParameterizedTest @ValueSource(strings = {"reason", "quote", "message", "criterion", "level", "na", "flag_value"})
    void invalidReviewerReplacementIsAtomic(String scenario) throws Exception {
        String criterion = scenario.equals("flag_value") ? "LOCAL_GROSS" : "LOCAL_CLARITY";
        var appeal = appeal(criterion);
        var replacement = answer(criterion, scenario.equals("flag_value") ? "yes" : "scale", 4);
        var body = resolution(replacement);
        switch (scenario) {
            case "reason" -> body.put("reason", " ");
            case "quote" -> ((ObjectNode) replacement.at("/evidence/0")).put("quote", "Invented quote");
            case "message" -> ((ObjectNode) replacement.at("/evidence/0")).put("message_id", "m9999");
            case "criterion" -> replacement.put("criterion_id", "LOCAL_GREETING").put("answer", "yes").putNull("value");
            case "level" -> replacement.put("value", 7);
            case "na" -> replacement.put("answer", "na").putNull("value");
        }
        var before = get();
        var history = db().queryForList("SELECT * FROM appeals WHERE evaluation_id=?", id);
        var failed = call("POST", route(appeal, 1), body);
        assertEquals(422, failed.status()); assertEquals("INVALID_INPUT", failed.body().at("/detail/code").asText());
        assertEquals(before, get());
        assertEquals(history, db().queryForList("SELECT * FROM appeals WHERE evaluation_id=?", id));
        immutable(get());
    }

    @Test void concurrentResolutionsHaveOneWinnerAndRequireExplicitFreshRevision() throws Exception {
        var clarity = appeal("LOCAL_CLARITY"); var greeting = appeal("LOCAL_GREETING");
        var barrier = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            var first = pool.submit(() -> { barrier.await(); return call("POST", route(clarity, 2), resolution(answer("LOCAL_CLARITY", "scale", 4))); });
            var second = pool.submit(() -> { barrier.await(); return call("POST", route(greeting, 2), resolution(null)); });
            barrier.countDown();
            var replies = List.of(first.get(10, TimeUnit.SECONDS), second.get(10, TimeUnit.SECONDS));
            assertEquals(List.of(200, 409), replies.stream().map(Reply::status).sorted().toList());
            var conflict = replies.stream().filter(r -> r.status() == 409).findFirst().orElseThrow();
            assertEquals("REVIEW_CONFLICT", conflict.body().at("/detail/code").asText());
        }
        var current = get(); assertEquals(3, current.get("review_revision").asLong());
        var open = new ArrayList<JsonNode>();
        for (var a : current.get("appeals")) if (a.get("status").asText().equals("open")) open.add(a);
        assertEquals(1, open.size());
        var pending = open.getFirst();
        assertEquals(409, call("POST", route(pending, 2), resolution(null)).status());
        assertEquals(current, get());
        resolve(pending, pending.get("criterion_id").asText().equals("LOCAL_CLARITY") ? answer("LOCAL_CLARITY", "scale", 4) : null);
        assertEquals(4, get().get("review_revision").asLong());
        assertEquals(60, get().at("/final_score/overall_score").asInt()); immutable(get());
    }

    @Test void arbitraryV2ManualEvaluationAndV1ReviewRemainPinnedAndMlPolicyRejectsV2() throws Exception {
        var v1 = ok("GET", "/api/checklists/synthetic-local?version=1", null, 200);
        var draft = draft();
        ((ArrayNode) draft.get("criteria")).addObject().put("id", "JURY_EXTRA_42").put("section_id", "quality")
            .put("title", "Arbitrary additional criterion").put("instruction", "Check whether the reply states opening time.")
            .put("kind", "binary").put("weight", 25).put("allow_na", false).putNull("na_rule").putArray("levels");
        var v2 = ok("PUT", "/api/checklists/synthetic-local?expected_version=1", draft, 200);
        assertEquals(2, v2.get("version").asInt());
        assertEquals(409, call("PUT", "/api/checklists/synthetic-local?expected_version=1", draft).status());
        assertEquals(v1, ok("GET", "/api/checklists/synthetic-local?version=1", null, 200));
        var manual = request.deepCopy(); manual.remove("request_id"); manual.put("checklist_version", 2);
        var answers = (ArrayNode) expected.get("answers").deepCopy(); answers.add(answer("JURY_EXTRA_42", "no", null)); manual.set("answers", answers);
        var saved = ok("POST", "/api/evaluations/manual", manual, 201);
        assertEquals("manual", saved.get("origin").asText()); assertEquals(2, saved.get("checklist_version").asInt());
        assertEquals(75, saved.at("/original_score/overall_score").asInt());
        assertEquals(5, saved.get("original_answers").size());
        assertEquals(422, call("POST", "/api/evaluations/" + id + "/appeals", Map.of("criterion_id", "JURY_EXTRA_42", "comment", "Only v2 has this criterion")).status());
        var changed = resolve(appeal("LOCAL_CLARITY"), answer("LOCAL_CLARITY", "scale", 4));
        assertEquals(60, changed.at("/final_score/overall_score").asInt()); assertEquals(4, changed.get("final_answers").size());
        assertEquals(saved, ok("GET", "/api/evaluations/" + saved.get("id").asText(), null, 200));
        var autoV2 = request.deepCopy().put("request_id", UUID.randomUUID().toString()).put("checklist_version", 2);
        var blocked = call("POST", "/api/evaluations/auto", autoV2);
        assertEquals(503, blocked.status()); assertEquals("PRIVACY_POLICY_UNCONFIGURED", blocked.body().at("/detail/code").asText());
        assertEquals(404, call("GET", "/api/evaluation-requests/" + autoV2.get("request_id").asText(), null).status());
        immutable(changed);
    }
}
