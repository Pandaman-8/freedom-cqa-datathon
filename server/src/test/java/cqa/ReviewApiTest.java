package cqa;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import cqa.repository.StorageInitializer;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import java.net.URI;
import java.net.http.*;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

/** Synthetic real HTTP/SQLite tests. Two independent applications share only the database file. */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ReviewApiTest {
    @TempDir static Path directory;
    private ServletWebServerApplicationContext app;
    private final ObjectMapper json = new ObjectMapper();
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private String base, evaluation, conversation;
    private JsonNode original;
    private int sequence;
    private Path database() { return directory.resolve("review.sqlite"); }
    private ServletWebServerApplicationContext boot() {
        return (ServletWebServerApplicationContext) new SpringApplicationBuilder(Application.class).run(
            "--server.port=0", "--cqa.db-path=" + database(), "--spring.main.banner-mode=off", "--logging.level.root=WARN");
    }
    private String url(ServletWebServerApplicationContext context) { return "http://127.0.0.1:" + context.getWebServer().getPort(); }
    @BeforeAll void start() { app = boot(); base = url(app); }
    @AfterAll void stop() { if (app != null) app.close(); client.close(); }
    private JdbcTemplate db() { return app.getBean(JdbcTemplate.class); }
    record Reply(int status, JsonNode body, String raw) {}
    private Reply at(String host, String method, String route, Object body) throws Exception {
        String payload = body == null ? null : body instanceof String s ? s : json.writeValueAsString(body);
        var request = HttpRequest.newBuilder(URI.create(host + route)).timeout(Duration.ofSeconds(20))
            .header("Content-Type", "application/json")
            .method(method, payload == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(payload)).build();
        var response = client.send(request, HttpResponse.BodyHandlers.ofString());
        return new Reply(response.statusCode(), response.body().isEmpty() ? NullNode.instance : json.readTree(response.body()), response.body());
    }
    private Reply call(String method, String route, Object body) throws Exception { return at(base, method, route, body); }
    private JsonNode ok(String method, String route, Object body, int status) throws Exception {
        var reply = call(method, route, body); assertEquals(status, reply.status(), reply.raw()); return reply.body();
    }
    private void error(Reply reply, int status, String code) {
        assertEquals(status, reply.status(), reply.raw()); assertEquals(code, reply.body().at("/detail/code").asText());
        assertFalse(reply.body().at("/detail/retryable").asBoolean());
        assertTrue(reply.body().at("/detail/request_id").isNull());
        for (String secret : List.of("SQLException", "org.sqlite", "SELECT ", "SYNTHETIC_SECRET", "example.invalid", "e\u0301 response", directory.toString()))
            assertFalse(reply.raw().contains(secret), "Error leaked data");
    }
    private ObjectNode answer(String criterion, String kind, Integer value) {
        ObjectNode answer = json.createObjectNode().put("criterion_id", criterion).put("answer", kind)
            .put("explanation", "Synthetic reviewer explanation.").putNull("value");
        if (value != null) answer.put("value", value);
        answer.putArray("evidence").addObject().put("message_id", "m0003").put("quote", " Synthetic e\u0301 response ");
        return answer;
    }
    private ObjectNode resolution(ObjectNode replacement) {
        ObjectNode result = json.createObjectNode().put("decision", replacement == null ? "confirm" : "change")
            .put("reason", "Synthetic review reason.");
        result.set("replacement", replacement == null ? NullNode.instance : replacement); return result;
    }
    private ObjectNode appealBody(String criterion) { return json.createObjectNode().put("criterion_id", criterion).put("comment", " Synthetic appeal comment "); }
    private JsonNode create(String criterion) throws Exception { return ok("POST", "/api/evaluations/" + evaluation + "/appeals", appealBody(criterion), 201); }
    private JsonNode get() throws Exception { return ok("GET", "/api/evaluations/" + evaluation, null, 200); }
    private String resolveRoute(String id, long revision) { return "/api/appeals/" + id + "/resolve?expected_revision=" + revision; }
    private JsonNode resolve(JsonNode appeal, ObjectNode replacement) throws Exception {
        return ok("POST", resolveRoute(appeal.get("id").asText(), get().get("review_revision").asLong()), resolution(replacement), 200);
    }
    private void intact(JsonNode result) {
        for (String field : List.of("original_answers", "original_score", "scoring_version", "checklist_key", "checklist_version", "origin", "created_at"))
            assertEquals(original.get(field), result.get(field), field);
    }
    private Map<String, Object> storedOriginal() {
        return db().queryForMap("SELECT * FROM evaluations WHERE id=?", evaluation);
    }
    private ObjectNode draft() throws Exception {
        ObjectNode result = (ObjectNode) ok("GET", "/api/checklists/chat-quality?version=1", null, 200);
        result.remove(List.of("key", "version")); return result;
    }
    @BeforeEach void syntheticEvaluation() throws Exception {
        conversation = "SYNTHETIC-REVIEW-" + ++sequence + ":example";
        ObjectNode source = json.createObjectNode().put("isSuccess", true).put("error", "");
        ObjectNode data = source.putObject("data").put("dataset_group_id", conversation.split(":")[0]).put("total_records", 1);
        ObjectNode record = data.putArray("records").addObject().put("conversation_id", "example").put("channel", "agent chat").put("language", "EN")
            .put("audio_url", "https://example.invalid/synthetic.wav?sig=SYNTHETIC_SECRET");
        var transcript = record.putArray("transcript");
        for (String role : List.of("client", "bot", "operator", "system"))
            transcript.addObject().put("timestamp", "00:01").put("speaker", role).put("text", " Synthetic e\u0301 response ");
        ok("POST", "/api/datasets/import", source, 200);
        ObjectNode manual = json.createObjectNode().put("conversation_id", conversation).put("checklist_key", "chat-quality").put("checklist_version", 1);
        var answers = manual.putArray("answers");
        for (JsonNode criterion : draft().get("criteria")) {
            String kind = criterion.get("kind").asText();
            var levels = criterion.get("levels");
            answers.add(answer(criterion.get("id").asText(), kind.equals("scale") ? "scale" : kind.equals("flag") ? "no" : "yes",
                kind.equals("scale") ? levels.get(levels.size() - 1).get("value").asInt() : null));
        }
        original = ok("POST", "/api/evaluations/manual", manual, 201); evaluation = original.get("id").asText();
        assertEquals(100, original.at("/original_score/overall_score").asInt());
    }

    @Test void createPreservesCommentAndShowsRealStatusAndRevision() throws Exception {
        assertEquals(original, get());
        var appeal = create("C04"); var current = get();
        assertEquals(" Synthetic appeal comment ", appeal.get("comment").asText());
        assertEquals(evaluation, appeal.get("evaluation_id").asText());
        assertEquals("open", appeal.get("status").asText()); assertTrue(appeal.get("decision").isNull());
        assertTrue(appeal.get("resolved_at").isNull()); assertEquals(1, appeal.get("created_revision").asLong());
        assertEquals("appealed", current.get("review_status").asText()); assertEquals(1, current.get("review_revision").asLong());
        assertEquals(appeal, current.get("appeals").get(0)); intact(current);
        assertEquals(current.get("original_score"), current.get("final_score"));
    }
    @ParameterizedTest @ValueSource(strings={"unknown", "blank", "unicode_blank", "long", "extra", "number", "null", "missing", "criterion_type", "duplicate_key"})
    void invalidCreatesLeaveNoRows(String test) throws Exception {
        var body = appealBody("C04"); Object payload = body;
        switch (test) {
            case "unknown" -> body.put("criterion_id", "MISSING");
            case "blank" -> body.put("comment", "");
            case "unicode_blank" -> body.put("comment", " \t\n\u0085\u00a0");
            case "long" -> body.put("comment", "😀".repeat(3001));
            case "extra" -> body.put("secret", "SYNTHETIC_SECRET");
            case "number" -> body.put("comment", 12);
            case "null" -> body.putNull("comment");
            case "missing" -> body.remove("comment");
            case "criterion_type" -> body.put("criterion_id", true);
            case "duplicate_key" -> payload = "{\"criterion_id\":\"C04\",\"comment\":\"one\",\"comment\":\"two\"}";
        }
        error(call("POST", "/api/evaluations/" + evaluation + "/appeals", payload), 422, "INVALID_INPUT");
        assertEquals(original, get());
        assertEquals(0, db().queryForObject("SELECT count(*) FROM evaluation_reviews WHERE evaluation_id=?", Integer.class, evaluation));
    }
    @Test void unicodeLimitCountsCodepointsAndUnknownEvaluationIs404() throws Exception {
        error(call("POST", "/api/evaluations/missing/appeals", appealBody("C04")), 404, "NOT_FOUND");
        var appeal = ok("POST", "/api/evaluations/" + evaluation + "/appeals", appealBody("C04").put("comment", "😀".repeat(3000)), 201);
        var body = resolution(null).put("reason", "😀".repeat(3000));
        ok("POST", resolveRoute(appeal.get("id").asText(), 1), body, 200);
        // SQLite length(TEXT) stops at NUL; API validation must still count all code points.
        var nul = ok("POST", "/api/evaluations/" + evaluation + "/appeals", appealBody("C04").put("comment", "\u0000Synthetic"), 201);
        assertEquals("\u0000Synthetic", nul.get("comment").asText());
        ok("POST", resolveRoute(nul.get("id").asText(), 3), resolution(null).put("reason", "\u0000Synthetic"), 200);
    }
    @Test void duplicateOpenRollsBackRevision() throws Exception {
        create("C04"); var before = get();
        error(call("POST", "/api/evaluations/" + evaluation + "/appeals", appealBody("C04")), 409, "REVIEW_CONFLICT");
        assertEquals(before, get());
    }
    @Test void confirmAllowsLegacyOmittedReplacementAndChangesNoAnswers() throws Exception {
        var appeal = create("C04"); var body = resolution(null); body.remove("replacement");
        var result = ok("POST", resolveRoute(appeal.get("id").asText(), 1), body, 200);
        assertEquals("reviewed", result.get("review_status").asText()); assertEquals(2, result.get("review_revision").asInt());
        assertEquals("confirm", result.at("/appeals/0/decision").asText()); assertEquals(body.get("reason"), result.at("/appeals/0/reason"));
        assertEquals(result.get("original_answers"), result.get("final_answers"));
        assertEquals(result.get("original_score"), result.get("final_score")); intact(result);
    }
    @Test void changeRecalculatesAndPreservesOriginalDatabaseBytes() throws Exception {
        var before = storedOriginal(); var replacement = answer("C04", "scale", 5);
        var result = resolve(create("C04"), replacement);
        assertEquals(85.0, result.at("/final_score/overall_score").asDouble());
        assertEquals(replacement, result.at("/final_answers/3")); assertEquals(replacement, result.at("/appeals/0/replacement"));
        assertEquals(before, storedOriginal()); intact(result);
        assertEquals(result, get());
        assertEquals(result, ok("GET", "/api/evaluations?conversation_id=" + conversation, null, 200).get(0));
    }
    @ParameterizedTest @ValueSource(strings={"missing_reason", "blank_reason", "null_reason", "long_reason", "reason_type", "missing_replacement", "confirm_replacement", "wrong_criterion", "bad_scale", "scale_string", "forbidden_na", "bad_kind", "bad_flag", "unknown_message", "forged_quote", "normalized_quote", "blank_quote", "extra", "nested_extra", "unknown_decision", "duplicate_key"})
    void invalidResolutionsLeaveHistoryAndRevisionUnchanged(String test) throws Exception {
        String criterion = test.equals("bad_flag") ? "C08" : "C06";
        var appeal = create(criterion); var before = get();
        var replacement = answer(criterion, criterion.equals("C08") ? "no" : "scale", criterion.equals("C08") ? null : 7);
        var body = resolution(replacement); Object payload = body;
        switch (test) {
            case "missing_reason" -> body.remove("reason");
            case "blank_reason" -> body.put("reason", "\u00a0\u0085\t");
            case "null_reason" -> body.putNull("reason");
            case "long_reason" -> body.put("reason", "x".repeat(3001));
            case "reason_type" -> body.put("reason", false);
            case "missing_replacement" -> body.remove("replacement");
            case "confirm_replacement" -> body.put("decision", "confirm");
            case "wrong_criterion" -> replacement.put("criterion_id", "C04");
            case "bad_scale" -> replacement.put("value", 6);
            case "scale_string" -> replacement.put("value", "7");
            case "forbidden_na", "bad_flag" -> replacement.put("answer", "na").putNull("value");
            case "bad_kind" -> replacement.put("answer", "yes").putNull("value");
            case "unknown_message" -> ((ObjectNode) replacement.at("/evidence/0")).put("message_id", "m9999");
            case "forged_quote" -> ((ObjectNode) replacement.at("/evidence/0")).put("quote", "synthetic forged response");
            case "normalized_quote" -> ((ObjectNode) replacement.at("/evidence/0")).put("quote", "Synthetic é response");
            case "blank_quote" -> ((ObjectNode) replacement.at("/evidence/0")).put("quote", " ");
            case "extra" -> body.put("secret", "SYNTHETIC_SECRET");
            case "nested_extra" -> replacement.put("overall_score", 100);
            case "unknown_decision" -> body.put("decision", "approve");
            case "duplicate_key" -> payload = "{\"decision\":\"confirm\",\"decision\":\"change\",\"reason\":\"x\"}";
        }
        error(call("POST", resolveRoute(appeal.get("id").asText(), 1), payload), 422, "INVALID_INPUT");
        assertEquals(before, get()); intact(get());
    }
    @ParameterizedTest @ValueSource(strings={"", "-1", "1.0", "true", "9223372036854775808", "999999999999999999999999999"})
    void revisionIsRequiredBoundedNonnegativeInteger(String revision) throws Exception {
        var appeal = create("C01"); var before = get();
        String route = "/api/appeals/" + appeal.get("id").asText() + "/resolve" + (revision.isEmpty() ? "" : "?expected_revision=" + revision);
        error(call("POST", route, resolution(null)), 422, "INVALID_INPUT"); assertEquals(before, get());
    }
    @Test void missingAndAlreadyResolvedAppealsAreExplicitErrors() throws Exception {
        error(call("POST", resolveRoute("missing", 0), resolution(null)), 404, "NOT_FOUND");
        var appeal = create("C01"); var result = resolve(appeal, null);
        error(call("POST", resolveRoute(appeal.get("id").asText(), 2), resolution(null)), 409, "REVIEW_CONFLICT");
        assertEquals(result, get());
    }
    @Test void naExcludesWeightAndFlagDoesNotPenalizeTotal() throws Exception {
        resolve(create("C01"), answer("C01", "no", null));
        var na = resolve(create("C03"), answer("C03", "na", null));
        assertEquals(80, na.at("/final_score/applicable_weight").asInt());
        assertEquals(87.5, na.at("/final_score/overall_score").asDouble());
        var flag = resolve(create("C08"), answer("C08", "yes", null));
        assertEquals(87.5, flag.at("/final_score/overall_score").asDouble());
        assertTrue(flag.at("/final_score/critical_violation").asBoolean());
        assertEquals("C08", flag.at("/final_score/critical_criterion_ids/0").asText()); intact(flag);
    }
    @Test void reappealConfirmKeepsPriorChangeThenNewestChangeWins() throws Exception {
        resolve(create("C04"), answer("C04", "scale", 0));
        var second = create("C04"); assertEquals(80, get().at("/final_score/overall_score").asInt());
        var confirmed = resolve(second, null); assertEquals(80, confirmed.at("/final_score/overall_score").asInt());
        var changed = resolve(create("C04"), answer("C04", "scale", 10));
        assertEquals(90, changed.at("/final_score/overall_score").asInt()); assertEquals(3, changed.get("appeals").size());
        for (int i = 0; i < 3; i++) {
            assertEquals(2*i+1, changed.get("appeals").get(i).get("created_revision").asInt());
            assertEquals(2*i+2, changed.get("appeals").get(i).get("resolved_revision").asInt());
        }
        intact(changed);
    }
    @Test void outOfCreationOrderResolutionsHaveStableSequenceAndOpenStatus() throws Exception {
        var first = create("C01"); var second = create("C04");
        var partial = resolve(second, answer("C04", "scale", 0));
        assertEquals("appealed", partial.get("review_status").asText()); assertEquals(80, partial.at("/final_score/overall_score").asInt());
        var result = resolve(first, answer("C01", "no", null));
        assertEquals(70, result.at("/final_score/overall_score").asInt());
        assertEquals(4, result.at("/appeals/0/resolved_revision").asInt()); assertEquals(3, result.at("/appeals/1/resolved_revision").asInt());
        assertEquals(result, get()); intact(result);
    }
    @Test void customChecklistRemainsPinnedAfterV2ChangesIdsAndWeights() throws Exception {
        String key = "synthetic-custom-" + sequence; var draft = draft();
        for (JsonNode c : draft.get("criteria")) ((ObjectNode)c).put("id", "X_" + c.get("id").asText());
        ok("POST", "/api/checklists/" + key, draft, 200);
        var manual = json.createObjectNode().put("conversation_id", conversation).put("checklist_key", key).put("checklist_version", 1);
        ArrayNode answers = original.get("original_answers").deepCopy();
        for (JsonNode a : answers) ((ObjectNode)a).put("criterion_id", "X_" + a.get("criterion_id").asText());
        manual.set("answers", answers); original = ok("POST", "/api/evaluations/manual", manual, 201); evaluation = original.get("id").asText();
        var appeal = create("X_C04");
        ((ObjectNode) draft.get("criteria").get(3)).put("id", "V2_ONLY").put("weight", 30);
        ok("PUT", "/api/checklists/" + key + "?expected_version=1", draft, 200);
        var result = resolve(appeal, answer("X_C04", "scale", 0));
        assertEquals(80, result.at("/final_score/overall_score").asInt()); assertEquals(1, result.get("checklist_version").asInt()); intact(result);
        error(call("POST", "/api/evaluations/" + evaluation + "/appeals", appealBody("V2_ONLY")), 422, "INVALID_INPUT");
    }
    @Test void staleReviewerCannotOverwriteOtherDecisionOrNewAppeal() throws Exception {
        var first = create("C01"); var beforeSecond = get(); var second = create("C04"); var current = get();
        error(call("POST", resolveRoute(first.get("id").asText(), beforeSecond.get("review_revision").asLong()), resolution(null)), 409, "REVIEW_CONFLICT");
        assertEquals(current, get()); var changed = resolve(second, answer("C04", "scale", 0));
        error(call("POST", resolveRoute(first.get("id").asText(), current.get("review_revision").asLong()), resolution(answer("C01", "no", null))), 409, "REVIEW_CONFLICT");
        assertEquals(changed, get());
        assertEquals(70, resolve(first, answer("C01", "no", null)).at("/final_score/overall_score").asInt());
    }
    private List<Reply> race(String other, String firstRoute, Object first, String secondRoute, Object second) throws Exception {
        try (var threads = Executors.newFixedThreadPool(2)) {
            var gate = new CountDownLatch(1);
            var a = threads.submit(() -> { gate.await(); return at(base, "POST", firstRoute, first); });
            var b = threads.submit(() -> { gate.await(); return at(other, "POST", secondRoute, second); });
            gate.countDown(); return List.of(a.get(20, TimeUnit.SECONDS), b.get(20, TimeUnit.SECONDS));
        }
    }
    private void statuses(List<Reply> replies, int winner) {
        assertEquals(List.of(winner, 409), replies.stream().map(Reply::status).sorted().toList());
        error(replies.stream().filter(r -> r.status() == 409).findFirst().orElseThrow(), 409, "REVIEW_CONFLICT");
    }
    @Test void concurrentCreatesAcrossIndependentApplicationsHaveOneWinner() throws Exception {
        try (var second = boot()) {
            String route = "/api/evaluations/" + evaluation + "/appeals";
            statuses(race(url(second), route, appealBody("C04"), route, appealBody("C04")), 201);
            assertEquals(1, get().get("appeals").size()); assertEquals(1, get().get("review_revision").asInt());
        }
    }
    @Test void concurrentResolutionsAcrossIndependentApplicationsHaveOneWinner() throws Exception {
        var appeal = create("C04"); String route = resolveRoute(appeal.get("id").asText(), 1);
        try (var second = boot()) {
            var replies = race(url(second), route, resolution(answer("C04", "scale", 0)), route, resolution(answer("C04", "scale", 10)));
            statuses(replies, 200); assertEquals(replies.stream().filter(r -> r.status() == 200).findFirst().orElseThrow().body(), get());
            assertEquals(2, get().get("review_revision").asInt()); assertEquals(1, get().get("appeals").size()); intact(get());
        }
    }
    @Test void concurrentDifferentCriteriaRejectStaleAndRetryCombinesBothChanges() throws Exception {
        var first = create("C01"); var secondAppeal = create("C04");
        try (var second = boot()) {
            var a = resolution(answer("C01", "no", null)); var b = resolution(answer("C04", "scale", 0));
            var replies = race(url(second), resolveRoute(first.get("id").asText(), 2), a, resolveRoute(secondAppeal.get("id").asText(), 2), b);
            statuses(replies, 200);
            int loser = replies.get(0).status() == 409 ? 0 : 1;
            ok("POST", resolveRoute((loser == 0 ? first : secondAppeal).get("id").asText(), 3), loser == 0 ? a : b, 200);
            assertEquals(70, get().at("/final_score/overall_score").asInt()); assertEquals(4, get().get("review_revision").asInt()); intact(get());
        }
    }
    @Test void sqlFailureAfterRevisionCasRollsBackWholeResolution() throws Exception {
        var appeal = create("C04"); var before = get(); String id = appeal.get("id").asText();
        db().execute("CREATE TRIGGER test_reject_resolution BEFORE UPDATE ON appeals WHEN OLD.id='" + id + "' BEGIN SELECT RAISE(ABORT,'synthetic_failure'); END");
        try {
            var failed = call("POST", resolveRoute(id, 1), resolution(answer("C04", "scale", 0)));
            assertEquals(500, failed.status()); assertEquals("", failed.raw()); assertEquals(before, get());
        } finally { db().execute("DROP TRIGGER test_reject_resolution"); }
        assertEquals(80, resolve(appeal, answer("C04", "scale", 0)).at("/final_score/overall_score").asInt());
    }
    @Test void sqlFailureAfterRevisionCasRollsBackAppealAndLazyHead() throws Exception {
        db().execute("CREATE TRIGGER test_reject_create BEFORE INSERT ON appeals WHEN NEW.evaluation_id='" + evaluation + "' BEGIN SELECT RAISE(ABORT,'synthetic_failure'); END");
        try {
            var failed = call("POST", "/api/evaluations/" + evaluation + "/appeals", appealBody("C04"));
            assertEquals(500, failed.status()); assertEquals("", failed.raw()); assertEquals(original, get());
            assertEquals(0, db().queryForObject("SELECT count(*) FROM evaluation_reviews WHERE evaluation_id=?", Integer.class, evaluation));
        } finally { db().execute("DROP TRIGGER test_reject_create"); }
    }
    @Test void databaseConstraintsProtectOriginalHistoryUniquenessAndForeignKeys() throws Exception {
        var appeal = create("C04"); String id = appeal.get("id").asText();
        assertThrows(org.springframework.dao.DataAccessException.class, () -> db().update("INSERT INTO appeals(id,evaluation_id,criterion_id,comment,status,created_at,created_revision) VALUES('duplicate',?,'C04','x','open','now',99)", evaluation));
        assertThrows(org.springframework.dao.DataAccessException.class, () -> db().update("INSERT INTO evaluation_reviews VALUES('missing',0)"));
        assertThrows(org.springframework.dao.DataAccessException.class, () -> db().update("INSERT INTO appeals(id,evaluation_id,criterion_id,comment,status,created_at,created_revision) VALUES('orphan','missing','C04','x','open','now',1)"));
        resolve(appeal, null);
        assertThrows(org.springframework.dao.DataAccessException.class, () -> db().update("UPDATE appeals SET reason='rewritten' WHERE id=?", id));
        assertThrows(org.springframework.dao.DataAccessException.class, () -> db().update("DELETE FROM appeals WHERE id=?", id));
        assertThrows(org.springframework.dao.DataAccessException.class, () -> db().update("UPDATE evaluations SET answers_json='{}' WHERE id=?", evaluation));
        assertThrows(org.springframework.dao.DataAccessException.class, () -> db().update("UPDATE evaluations SET score_json='{}' WHERE id=?", evaluation));
        assertThrows(org.springframework.dao.DataAccessException.class, () -> db().update("DELETE FROM evaluations WHERE id=?", evaluation));
        assertThrows(org.springframework.dao.DataAccessException.class, () -> db().update("UPDATE evaluation_reviews SET revision=0 WHERE evaluation_id=?", evaluation));
    }
    @Test void unsupportedStoredScorerFailsExplicitlyWithoutWritingOrRecalculating() throws Exception {
        String unknown = UUID.randomUUID().toString();
        db().update("INSERT INTO evaluations SELECT ?,conversation_id,checklist_key,checklist_version,origin,'future-score/99',answers_json,'{}',created_at FROM evaluations WHERE id=?", unknown, evaluation);
        var reply = call("GET", "/api/evaluations/" + unknown, null); error(reply, 409, "REVIEW_CONFLICT");
        assertTrue(reply.body().at("/detail/message").asText().contains("scoring version is not supported"));
        error(call("POST", "/api/evaluations/" + unknown + "/appeals", appealBody("C04")), 409, "REVIEW_CONFLICT");
        error(call("GET", "/api/evaluations?conversation_id=" + conversation, null), 409, "REVIEW_CONFLICT");
        assertEquals(0, db().queryForObject("SELECT count(*) FROM evaluation_reviews WHERE evaluation_id=?", Integer.class, unknown));
        assertEquals(0, db().queryForObject("SELECT count(*) FROM appeals WHERE evaluation_id=?", Integer.class, unknown));
    }
    @Test void restartAndRepeatedInitializationPreserveOriginalSourceHistoryAndFinal() throws Exception {
        var snapshot = storedOriginal();
        var source = db().queryForMap("SELECT * FROM conversations WHERE id=?", conversation);
        resolve(create("C04"), answer("C04", "scale", 0)); resolve(create("C04"), null); create("C08");
        var before = get(); app.getBean(StorageInitializer.class).afterPropertiesSet(); assertEquals(before, get());
        app.close(); app = boot(); base = url(app);
        assertEquals(before, get()); assertEquals(snapshot, storedOriginal());
        assertEquals(source, db().queryForMap("SELECT * FROM conversations WHERE id=?", conversation));
        assertEquals(before, ok("GET", "/api/evaluations?conversation_id=" + conversation, null, 200).get(0));
        error(call("POST", resolveRoute(before.at("/appeals/0/id").asText(), before.get("review_revision").asLong()), resolution(null)), 409, "REVIEW_CONFLICT");
    }
}
