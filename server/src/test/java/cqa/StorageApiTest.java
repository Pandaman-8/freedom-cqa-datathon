package cqa;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import cqa.api.ApiModels.*;
import cqa.dto.*;
import cqa.service.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.math.BigInteger;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

/** Real loopback HTTP, isolated file SQLite, including closing/restarting the application. */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class StorageApiTest {
    @TempDir static Path directory;
    private ServletWebServerApplicationContext app;
    private String base;
    private final ObjectMapper json = new ObjectMapper();
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private int sequence;
    private String group;

    @BeforeAll void start() { boot(); }
    void boot() {
        app = (ServletWebServerApplicationContext) new SpringApplicationBuilder(Application.class).run(
            "--server.port=0", "--cqa.db-path=" + directory.resolve("nested/storage.sqlite"),
            "--spring.main.banner-mode=off", "--logging.level.root=WARN");
        base = "http://127.0.0.1:" + app.getWebServer().getPort();
    }
    @AfterAll void stop() { if (app != null) app.close(); client.close(); }
    @BeforeEach void uniqueGroup() { group = "SYNTHETIC-" + ++sequence; }
    record Reply(int status, JsonNode body, String raw) {}
    Reply call(String method, String route, Object body) throws Exception {
        return raw(method, route, body == null ? null : json.writeValueAsString(body), "application/json");
    }
    Reply raw(String method, String route, String body, String contentType) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create(base + route)).timeout(Duration.ofSeconds(20));
        if (body != null) builder.header("Content-Type", contentType);
        builder.method(method, body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(body));
        var response = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        JsonNode parsed = response.body().isEmpty() || !response.headers().firstValue("content-type").orElse("").contains("json")
            ? NullNode.instance : json.readTree(response.body());
        return new Reply(response.statusCode(), parsed, response.body());
    }
    JsonNode ok(String method, String route, Object body, int status) throws Exception {
        Reply reply = call(method, route, body); assertEquals(status, reply.status(), reply.raw()); return reply.body();
    }
    ObjectNode seed() throws Exception { return (ObjectNode) ok("GET", "/api/checklists/chat-quality?version=1", null, 200); }
    ObjectNode draft() throws Exception { ObjectNode result = seed().deepCopy(); result.remove(List.of("key","version")); return result; }
    ObjectNode dataset() {
        ObjectNode root = json.createObjectNode().put("error", "").put("isSuccess", true);
        ObjectNode data = root.putObject("data").put("dataset_group_id", group).put("total_records", 3);
        ArrayNode records = data.putArray("records");
        for (String language : List.of("EN","KZ","RU")) {
            ObjectNode record = records.addObject().put("conversation_id", language).put("language", language)
                .put("channel", language.equals("RU") ? "voice call" : "agent chat").putNull("audio_url");
            String time = language.equals("RU") ? "2026-11-07T10:00:00+05:00" : "00:01";
            ArrayNode turns = record.putArray("transcript");
            for (String role : List.of("client","bot","operator","system","operator")) {
                turns.addObject().put("timestamp", time).put("speaker", role)
                    .put("text", language.equals("EN") ? " Synthetic e\u0301 response " : language.equals("KZ") ? " Сәлем " : " Здравствуйте ");
            }
        }
        return root;
    }
    String importData() throws Exception { ok("POST", "/api/datasets/import", dataset(), 200); return group + ":EN"; }
    ObjectNode manual(String conversation) throws Exception {
        ObjectNode body = json.createObjectNode().put("conversation_id", conversation).put("checklist_key", "chat-quality").put("checklist_version", 1);
        ArrayNode answers = body.putArray("answers");
        for (JsonNode criterion : seed().get("criteria")) {
            ObjectNode answer = answers.addObject().put("criterion_id", criterion.get("id").asText())
                .put("answer", criterion.get("kind").asText().equals("scale") ? "scale" : criterion.get("kind").asText().equals("flag") ? "no" : "yes")
                .putNull("value").put("explanation", "Synthetic manual assessment.");
            if (answer.get("answer").asText().equals("scale")) {
                JsonNode levels = criterion.get("levels"); answer.set("value", levels.get(levels.size()-1).get("value"));
            }
            answer.putArray("evidence").addObject().put("message_id", "m0003").put("quote", "Synthetic e\u0301 response");
        }
        return body;
    }
    void error(Reply reply, int status, String code) {
        assertEquals(status, reply.status(), reply.raw()); assertEquals(code, reply.body().path("detail").path("code").asText());
        assertFalse(reply.body().path("detail").path("retryable").asBoolean());
        assertTrue(reply.body().path("detail").has("request_id"));
    }

    @Test void firstStartupCreatesFileSeedAndConnectionPragmas() throws Exception {
        assertTrue(Files.isRegularFile(directory.resolve("nested/storage.sqlite")));
        JsonNode official = json.readTree(Path.of("../backend/app/seed/chat_quality.json").toFile());
        assertEquals(official, seed());
        var db = app.getBean(JdbcTemplate.class);
        assertEquals(1, db.queryForObject("PRAGMA foreign_keys", Integer.class));
        assertEquals(5000, db.queryForObject("PRAGMA busy_timeout", Integer.class));
        assertEquals("wal", db.queryForObject("PRAGMA journal_mode", String.class));
        assertEquals(8, seed().get("criteria").size());
        app.getBean(com.zaxxer.hikari.HikariDataSource.class).getHikariPoolMXBean().softEvictConnections();
        assertEquals(1, db.queryForObject("PRAGMA foreign_keys", Integer.class));
        assertEquals(5000, db.queryForObject("PRAGMA busy_timeout", Integer.class));
    }
    @Test void importPreservesLanguagesRolesTimestampsDuplicatesAndIds() throws Exception {
        ObjectNode source = dataset();
        JsonNode imported = ok("POST", "/api/datasets/import", source, 200);
        assertEquals(3, imported.get("imported_records").asInt());
        for (JsonNode record : source.path("data").get("records")) {
            String id = group + ":" + record.get("conversation_id").asText();
            JsonNode stored = ok("GET", "/api/conversations/" + id, null, 200);
            assertEquals(record.get("transcript"), stored.get("transcript"));
            assertEquals(record.get("language"), stored.get("language"));
            assertEquals(record.get("channel"), stored.get("channel"));
            assertEquals(5, stored.get("message_count").asInt());
            for (int i=0;i<5;i++) {
                ObjectNode turn = record.get("transcript").get(i).deepCopy(); turn.put("id", "m000"+(i+1));
                assertEquals(turn, stored.get("messages").get(i));
            }
        }
    }
    @Test void repeatedIdenticalImportIsIdempotentAndGroupsRemainDistinct() throws Exception {
        ObjectNode source = dataset();
        ok("POST", "/api/datasets/import", source, 200);
        JsonNode before = ok("GET", "/api/conversations", null, 200);
        ok("POST", "/api/datasets/import", source, 200);
        assertEquals(before, ok("GET", "/api/conversations", null, 200));
        ((ObjectNode) source.get("data")).put("dataset_group_id", group + "-CONTROL");
        ok("POST", "/api/datasets/import", source, 200);
        ok("GET", "/api/conversations/" + group + "-CONTROL:EN", null, 200);
    }
    @Test void conflictingSecondRecordRollsBackFirstInsert() throws Exception {
        importData();
        ObjectNode batch = dataset(); ArrayNode records = (ArrayNode) batch.path("data").get("records");
        ((ObjectNode) records.get(0)).put("conversation_id", "NEW");
        ((ObjectNode) records.get(1).path("transcript").get(0)).put("text", "Changed existing text");
        error(call("POST", "/api/datasets/import", batch), 409, "VERSION_CONFLICT");
        error(call("GET", "/api/conversations/" + group + ":NEW", null), 404, "NOT_FOUND");
        assertEquals(" Сәлем ", ok("GET", "/api/conversations/" + group + ":KZ", null, 200).path("transcript").get(0).get("text").asText());
    }
    @Test void changedAudioIsAlsoAConflict() throws Exception {
        importData(); ObjectNode source = dataset();
        ((ObjectNode) source.path("data").path("records").get(0)).put("audio_url", "https://example.invalid/synthetic.wav");
        error(call("POST", "/api/datasets/import", source),409,"VERSION_CONFLICT");
    }
    @Test void malformedEnvelopeCountDuplicatesAndRolesAreRejectedAtomically() throws Exception {
        List<ObjectNode> invalid = new ArrayList<>();
        ObjectNode count = dataset(); ((ObjectNode) count.get("data")).put("total_records",4); invalid.add(count);
        ObjectNode duplicate = dataset(); ((ObjectNode) duplicate.path("data").path("records").get(1)).put("conversation_id","EN"); invalid.add(duplicate);
        ObjectNode failed = dataset().put("isSuccess",false); invalid.add(failed);
        ObjectNode err = dataset().put("error","Synthetic failure"); invalid.add(err);
        ObjectNode role = dataset(); ((ObjectNode) role.at("/data/records/2/transcript/0")).put("speaker","unknown"); invalid.add(role);
        ObjectNode coerced = dataset(); ((ObjectNode) coerced.get("data")).put("total_records","3"); invalid.add(coerced);
        for (ObjectNode body : invalid) error(call("POST","/api/datasets/import",body),422,"INVALID_INPUT");
        error(call("GET","/api/conversations/"+group+":EN",null),404,"NOT_FOUND");
    }
    @Test void checklistHistoryAndExpectedVersionConflicts() throws Exception {
        String key = group; ObjectNode first = draft(); first.put("title","First");
        assertEquals(1, ok("POST","/api/checklists/"+key,first,200).get("version").asInt());
        ObjectNode second = first.deepCopy().put("title","Second");
        assertEquals(2,ok("PUT","/api/checklists/"+key+"?expected_version=1",second,200).get("version").asInt());
        assertEquals("First",ok("GET","/api/checklists/"+key+"?version=1",null,200).get("title").asText());
        assertEquals("Second",ok("GET","/api/checklists/"+key,null,200).get("title").asText());
        error(call("PUT","/api/checklists/"+key+"?expected_version=1",first),409,"VERSION_CONFLICT");
        error(call("PUT","/api/checklists/"+key,first),422,"INVALID_INPUT");
        error(call("POST","/api/checklists/"+key,first),409,"VERSION_CONFLICT");
        error(call("POST","/api/checklists/chat-quality",first),409,"VERSION_CONFLICT");
        error(call("GET","/api/checklists/"+key+"?version=3",null),404,"NOT_FOUND");
    }
    @Test void concurrentEditsHaveOneWinner() throws Exception {
        String key = group; ObjectNode body = draft(); ok("POST","/api/checklists/"+key,body,200);
        try (var threads = Executors.newFixedThreadPool(2)) {
            var gate = new CountDownLatch(1);
            Callable<Integer> edit = () -> { gate.await(); return call("PUT","/api/checklists/"+key+"?expected_version=1",body).status(); };
            Future<Integer> a=threads.submit(edit), b=threads.submit(edit); gate.countDown();
            var statuses = new ArrayList<>(List.of(a.get(20,TimeUnit.SECONDS),b.get(20,TimeUnit.SECONDS))); Collections.sort(statuses);
            assertEquals(List.of(200,409),statuses);
        }
        assertEquals(2,ok("GET","/api/checklists/"+key,null,200).get("version").asInt());
    }
    @Test void draftsCannotAssignVersionAndNeedValidDynamicCriteria() throws Exception {
        ObjectNode invalid=draft().put("version",999);
        error(call("POST","/api/checklists/"+group,invalid),422,"INVALID_INPUT");
        ObjectNode dynamic=draft(); ((ObjectNode) dynamic.path("criteria").get(0)).put("id","JURY-NEW").put("weight",27);
        assertEquals("JURY-NEW",ok("POST","/api/checklists/"+group,dynamic,200).get("criteria").get(0).get("id").asText());
        ObjectNode unknown=draft(); ((ObjectNode) unknown.path("criteria").get(0)).put("kind","text");
        error(call("POST","/api/checklists/"+group+"-bad",unknown),422,"INVALID_INPUT");
    }
    @Test void manualScoresAndHistoryUseOriginalSnapshots() throws Exception {
        String conversation=importData(); ObjectNode body=manual(conversation);
        JsonNode evaluation=ok("POST","/api/evaluations/manual",body,201);
        assertEquals(100,evaluation.path("original_score").path("overall_score").asInt());
        assertEquals("cqa-score/1",evaluation.path("scoring_version").asText());
        assertEquals("manual",evaluation.path("origin").asText());
        assertEquals(evaluation.get("original_score"),evaluation.get("final_score"));
        assertEquals(evaluation.get("original_answers"),evaluation.get("final_answers"));
        assertEquals(0,evaluation.get("appeals").size()); assertEquals("evaluated",evaluation.get("review_status").asText());
        assertEquals(evaluation,ok("GET","/api/evaluations/"+evaluation.get("id").asText(),null,200));
        assertEquals(evaluation,ok("GET","/api/evaluations?conversation_id="+conversation,null,200).get(0));
    }
    @Test void pinnedV1SurvivesV2CreatedBeforeSave() throws Exception {
        String conversation=importData(), key=group;
        ObjectNode original=draft(); ok("POST","/api/checklists/"+key,original,200);
        var service=app.getBean(EvaluationService.class);
        var pinned=service.pin(conversation,key,BigInteger.ONE);
        assertFalse(TransactionSynchronizationManager.isActualTransactionActive());
        ObjectNode changed=original.deepCopy(); ((ObjectNode) changed.path("criteria").get(0)).put("id","V2-only");
        ok("PUT","/api/checklists/"+key+"?expected_version=1",changed,200);
        var codec=app.getBean(ContractJson.class);
        var request=codec.shape(manual(conversation),ManualRequest.class);
        var saved=service.saveManual(pinned,request.answers());
        assertEquals(BigInteger.ONE,saved.checklist_version());
        assertEquals("C01",saved.original_answers().getFirst().criterion_id());
        JsonNode read=ok("GET","/api/evaluations/"+saved.id(),null,200);
        assertEquals(1,read.get("checklist_version").asInt()); assertEquals(100,read.path("original_score").get("overall_score").asInt());
        ObjectNode historical=manual(conversation).put("checklist_key",key);
        ok("POST","/api/evaluations/manual",historical,201);
    }
    @Test void invalidAnswersEvidenceAndClientTotalsNeverPersist() throws Exception {
        String conversation=importData(); ObjectNode valid=manual(conversation);
        List<ObjectNode> invalid=new ArrayList<>();
        ObjectNode level=valid.deepCopy(); ((ObjectNode) level.path("answers").get(3)).put("value",6); invalid.add(level);
        ObjectNode na=valid.deepCopy(); ((ObjectNode) na.path("answers").get(0)).put("answer","na"); invalid.add(na);
        ObjectNode quote=valid.deepCopy(); ((ObjectNode) quote.at("/answers/0/evidence/0")).put("quote","fabricated"); invalid.add(quote);
        ObjectNode id=valid.deepCopy(); ((ObjectNode) id.at("/answers/0/evidence/0")).put("message_id","m9999"); invalid.add(id);
        ObjectNode partial=valid.deepCopy(); ((ArrayNode) partial.get("answers")).remove(0); invalid.add(partial);
        ObjectNode duplicate=valid.deepCopy(); ((ObjectNode) duplicate.path("answers").get(1)).put("criterion_id","C01"); invalid.add(duplicate);
        invalid.add(valid.deepCopy().put("total",100)); invalid.add(valid.deepCopy().put("origin","model"));
        ObjectNode unpinned=valid.deepCopy(); unpinned.remove("checklist_version"); invalid.add(unpinned);
        for(ObjectNode body:invalid) error(call("POST","/api/evaluations/manual",body),422,"INVALID_INPUT");
        assertEquals(0,ok("GET","/api/evaluations?conversation_id="+conversation,null,200).size());
    }
    @Test void autoValidatesPinnedResourcesAndReturns501WithoutEvaluation() throws Exception {
        String conversation=importData(), requestId=UUID.randomUUID().toString();
        ObjectNode body=json.createObjectNode().put("request_id",requestId).put("conversation_id",conversation)
            .put("checklist_key","chat-quality").put("checklist_version",1);
        Reply reply=call("POST","/api/evaluations/auto",body); error(reply,501,"EVALUATOR_UNCONFIGURED");
        assertEquals(requestId,reply.body().path("detail").get("request_id").asText());
        assertEquals(0,ok("GET","/api/evaluations?conversation_id="+conversation,null,200).size());
        error(call("POST","/api/evaluations/auto",body.deepCopy().put("checklist_version",999)),404,"NOT_FOUND");
        ObjectNode missing=body.deepCopy(); missing.remove("checklist_version");
        Reply invalid=call("POST","/api/evaluations/auto",missing); error(invalid,422,"INVALID_INPUT");
        assertEquals(requestId,invalid.body().path("detail").get("request_id").asText());
    }
    @Test void restartKeepsSeedVersionsConversationsAndEvaluations() throws Exception {
        String conversation=importData(), key=group;
        ObjectNode draft=draft(); ok("POST","/api/checklists/"+key,draft,200);
        ok("PUT","/api/checklists/"+key+"?expected_version=1",draft.deepCopy().put("title","Retained v2"),200);
        JsonNode saved=ok("POST","/api/evaluations/manual",manual(conversation),201);
        JsonNode source=ok("GET","/api/conversations/"+conversation,null,200);
        JsonNode originalSeed=seed();
        JsonNode latest=ok("GET","/api/checklists/chat-quality",null,200);
        int next=latest.get("version").asInt()+1;
        ok("PUT","/api/checklists/chat-quality?expected_version="+(next-1),draft.deepCopy().put("title","User revision survives seed"),200);
        app.close(); boot();
        assertEquals(source,ok("GET","/api/conversations/"+conversation,null,200));
        assertEquals(saved,ok("GET","/api/evaluations/"+saved.get("id").asText(),null,200));
        assertEquals(originalSeed,seed()); assertEquals(2,ok("GET","/api/checklists/"+key,null,200).get("version").asInt());
        assertEquals(next,ok("GET","/api/checklists/chat-quality",null,200).get("version").asInt());
        assertEquals(1,app.getBean(JdbcTemplate.class).queryForObject("SELECT count(*) FROM checklists WHERE key='chat-quality' AND version='1'",Integer.class));
    }
    @Test void immutableRowsAndForeignKeysAreEnforced() throws Exception {
        String conversation=importData(); var db=app.getBean(JdbcTemplate.class);
        JsonNode saved=ok("POST","/api/evaluations/manual",manual(conversation),201);
        assertThrows(org.springframework.dao.DataAccessException.class,()->db.update("UPDATE checklists SET payload_json='{}' WHERE key='chat-quality'"));
        assertThrows(org.springframework.dao.DataAccessException.class,()->db.update("DELETE FROM conversations WHERE id=?",conversation));
        assertThrows(org.springframework.dao.DataAccessException.class,()->db.update("UPDATE evaluations SET score_json='{}' WHERE id=?",saved.get("id").asText()));
        assertThrows(org.springframework.dao.DataAccessException.class,()->db.update("INSERT INTO checklist_heads(key,version) VALUES('missing','99')"));
    }
    @Test void safeStatusMappingsAndBoundedBodies() throws Exception {
        for(String path:List.of("/api/conversations/missing","/api/checklists/missing","/api/evaluations/missing")) error(call("GET",path,null),404,"NOT_FOUND");
        error(raw("POST","/api/datasets/import","{\"secret\":\"SYNTHETIC_SECRET\", broken","application/json"),422,"INVALID_INPUT");
        error(raw("POST","/api/datasets/import","{} {}","application/json"),422,"INVALID_INPUT");
        error(raw("POST","/api/datasets/import","{}","text/plain"),422,"INVALID_INPUT");
        error(call("GET","/api/checklists/chat-quality?version=nope",null),422,"INVALID_INPUT");
        Reply oversized=raw("POST","/api/datasets/import"," ".repeat(16*1024*1024+1),"application/json");
        error(oversized,413,"PAYLOAD_TOO_LARGE");
        Reply secret=raw("POST","/api/datasets/import","{\"secret\":\"SYNTHETIC_SECRET\"}","application/json");
        assertFalse(secret.raw().contains("SYNTHETIC_SECRET")); assertFalse(secret.raw().contains("SQLException")); assertFalse(secret.raw().contains(directory.toString()));
    }

    @Test void chunkedBodyIsBoundedWithoutContentLength() throws Exception {
        var request=HttpRequest.newBuilder(URI.create(base+"/api/evaluations/manual")).timeout(Duration.ofSeconds(20))
            .header("Content-Type","application/json")
            .POST(HttpRequest.BodyPublishers.ofInputStream(()->new java.io.ByteArrayInputStream(new byte[1024*1024+1]))).build();
        var response=client.send(request,HttpResponse.BodyHandlers.ofString());
        assertEquals(413,response.statusCode());
        assertEquals("PAYLOAD_TOO_LARGE",json.readTree(response.body()).path("detail").path("code").asText());
    }

    @Test void writersFromTwoApplicationConnectionsCannotLoseChecklistUpdates() throws Exception {
        ObjectNode body=draft(); String key=group;
        ok("POST","/api/checklists/"+key,body,200);
        try (var second=(ServletWebServerApplicationContext)new SpringApplicationBuilder(Application.class).run(
                "--server.port=0","--cqa.db-path="+directory.resolve("nested/storage.sqlite"),
                "--spring.main.banner-mode=off","--logging.level.root=WARN");
             var threads=Executors.newFixedThreadPool(2)) {
            String other="http://127.0.0.1:"+second.getWebServer().getPort();
            var gate=new CountDownLatch(1);
            Future<Integer> first=threads.submit(()->{gate.await();return call("PUT","/api/checklists/"+key+"?expected_version=1",body).status();});
            Future<Integer> another=threads.submit(()->{
                gate.await();
                var request=HttpRequest.newBuilder(URI.create(other+"/api/checklists/"+key+"?expected_version=1"))
                    .timeout(Duration.ofSeconds(20)).header("Content-Type","application/json")
                    .PUT(HttpRequest.BodyPublishers.ofString(body.toString())).build();
                return client.send(request,HttpResponse.BodyHandlers.discarding()).statusCode();
            });
            gate.countDown();
            var statuses=new ArrayList<>(List.of(first.get(20,TimeUnit.SECONDS),another.get(20,TimeUnit.SECONDS)));
            Collections.sort(statuses); assertEquals(List.of(200,409),statuses);
        }
        assertEquals(2,ok("GET","/api/checklists/"+key,null,200).get("version").asInt());
    }
}
