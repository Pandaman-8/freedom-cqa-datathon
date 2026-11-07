package cqa;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import com.sun.net.httpserver.*;
import cqa.api.ApiModels.AutoRequest;
import cqa.dto.*;
import cqa.ml.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.test.system.*;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;

/** Real Java HTTP/SQLite with a fake Python transport. Never real inference. */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@ExtendWith(OutputCaptureExtension.class)
class AutoEvaluationApiTest {
    @TempDir static Path temp;
    private final ObjectMapper json=new ObjectMapper();
    private final HttpClient http=HttpClient.newHttpClient();
    private final AtomicReference<String> mode=new AtomicReference<>("ok");
    private final AtomicInteger calls=new AtomicInteger();
    private volatile JsonNode received;
    private volatile CountDownLatch entered,release;
    private HttpServer fake;
    private ExecutorService workers;
    private ServletWebServerApplicationContext app;
    private ObjectNode fixture,expected;
    private String base,endpoint;
    private JdbcTemplate db(){return app.getBean(JdbcTemplate.class);}
    private void boot(){
        app=(ServletWebServerApplicationContext)new SpringApplicationBuilder(Application.class).run(
            "--server.port=0","--cqa.db-path="+temp.resolve("auto.sqlite"),"--cqa.organizer-url=", "--cqa.ml-url="+endpoint,
            "--cqa.ml-connect-timeout-ms=500","--cqa.ml-response-timeout-ms=1500","--spring.main.banner-mode=off","--logging.level.root=WARN");
        base="http://127.0.0.1:"+app.getWebServer().getPort();
    }
    @BeforeAll void start() throws Exception {
        Path fixtures=Path.of("../ml-service/tests/fixtures/en_public_na");
        fixture=(ObjectNode)json.readTree(fixtures.resolve("request.json").toFile());
        expected=(ObjectNode)json.readTree(fixtures.resolve("expected.json").toFile());
        fake=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        workers=Executors.newCachedThreadPool();fake.setExecutor(workers);fake.createContext("/v1/evaluate",this::respond);fake.start();
        endpoint="http://127.0.0.1:"+fake.getAddress().getPort()+"/v1/evaluate";boot();
        assertEquals(200,call("POST","/api/datasets/import",dataset(fixture.get("conversation"))).code());
        var draft=fixture.get("checklist").deepCopy();((ObjectNode)draft).remove(List.of("key","version"));
        assertEquals(200,call("POST","/api/checklists/synthetic-local",draft).code());
    }
    @AfterAll void stop(){if(app!=null)app.close();fake.stop(0);workers.shutdownNow();http.close();}
    @BeforeEach void reset(){mode.set("ok");calls.set(0);received=null;entered=new CountDownLatch(1);release=new CountDownLatch(1);}
    private ObjectNode dataset(JsonNode source){
        var root=json.createObjectNode().put("isSuccess",true).put("error","");
        var data=root.putObject("data").put("dataset_group_id",source.get("dataset_group_id").asText()).put("total_records",1);
        var record=data.putArray("records").addObject().put("conversation_id",source.get("conversation_id").asText())
            .put("channel",source.get("channel").asText()).put("language",source.get("language").asText()).put("audio_url","https://example.invalid/PRIVATE_AUDIO");
        var turns=record.putArray("transcript");for(var m:source.get("messages")){var turn=(ObjectNode)m.deepCopy();turn.remove("id");turns.add(turn);}
        return root;
    }
    private ObjectNode payload(){return json.createObjectNode().put("request_id",UUID.randomUUID().toString())
        .put("conversation_id",fixture.at("/conversation/id").asText()).put("checklist_key","synthetic-local").put("checklist_version",1);}
    private void respond(HttpExchange e) throws IOException {
        calls.incrementAndGet();var input=json.readTree(e.getRequestBody());received=input;String current=mode.get();entered.countDown();
        try{
            if(current.equals("drop"))return;
            if(current.equals("block"))release.await(3,TimeUnit.SECONDS);
            if(current.equals("slow_headers"))Thread.sleep(1900);
            ObjectNode result=json.createObjectNode().put("contract_version","2.0.0").put("request_id",input.get("request_id").asText())
                .put("conversation_id",input.at("/conversation/id").asText()).put("checklist_key",input.at("/checklist/key").asText())
                .set("checklist_version",input.at("/checklist/version"));
            result.set("answers",expected.get("answers").deepCopy());
            var diagnostics=((ObjectNode)result).putObject("diagnostics").put("provider","local-test").put("model","fake-http")
                .put("prompt_version","synthetic-test").put("attempt_count",1).putNull("input_tokens").putNull("output_tokens")
                .putNull("estimated_cost_usd").put("latency_ms",1);diagnostics.putArray("warnings");
            var object=(ObjectNode)result;var answer=(ObjectNode)result.at("/answers/0");
            switch(current){
                case "request_id" -> object.put("request_id",UUID.randomUUID().toString());
                case "contract_version" -> object.put("contract_version","1.0.0");
                case "conversation_id" -> object.put("conversation_id","OTHER");
                case "checklist_key" -> object.put("checklist_key","OTHER");
                case "checklist_version" -> object.put("checklist_version",2);
                case "missing_answer" -> ((ArrayNode)result.get("answers")).remove(0);
                case "duplicate_answer" -> ((ArrayNode)result.get("answers")).set(1,answer.deepCopy());
                case "evidence" -> ((ObjectNode)answer.at("/evidence/0")).put("quote","PRIVATE_UPSTREAM_TEXT");
                case "message_id" -> ((ObjectNode)answer.at("/evidence/0")).put("message_id","m9999");
                case "empty_evidence" -> answer.putArray("evidence");
                case "scale" -> ((ObjectNode)result.at("/answers/2")).put("value",3);
                case "na" -> answer.put("answer","na");
                case "unknown_field" -> answer.put("secret","PRIVATE_UPSTREAM_TEXT");
                case "numeric_string" -> diagnostics.put("attempt_count","1");
                case "zero_attempts" -> diagnostics.put("attempt_count",0);
            }
            int status=200;byte[] bytes=json.writeValueAsBytes(result);
            if(current.startsWith("error")){
                status=503;String echo=current.equals("error_bad_echo")?UUID.randomUUID().toString():input.get("request_id").asText();
                bytes=json.writeValueAsBytes(Map.of("detail",Map.of("code","EVALUATOR_BUSY","message","PRIVATE_UPSTREAM_TEXT","retryable",true,"request_id",echo)));
            }
            if(current.equals("redirect")){status=307;e.getResponseHeaders().set("Location",endpoint);}
            if(current.equals("duplicate_json"))bytes=("{\"contract_version\":\"2.0.0\","+new String(bytes,StandardCharsets.UTF_8).substring(1)).getBytes(StandardCharsets.UTF_8);
            if(current.equals("invalid_utf8"))bytes=new byte[]{(byte)0xc3,0x28};
            if(current.equals("huge"))bytes=new byte[ContractJson.RESPONSE_LIMIT+1];
            e.getResponseHeaders().set("Content-Type",current.equals("wrong_type")?"text/html":"application/json; charset=utf-8");
            e.sendResponseHeaders(status,current.equals("slow_body")||current.equals("huge")?0:bytes.length);
            if(current.equals("slow_body")){e.getResponseBody().write('{');e.getResponseBody().flush();Thread.sleep(1900);}
            e.getResponseBody().write(bytes);
        }catch(InterruptedException interrupted){Thread.currentThread().interrupt();}
        catch(IOException ignored){/* Expected cancellation of bounded/failed requests. */}
        finally{e.close();}
    }
    record Reply(int code,JsonNode body,String raw){}
    private Reply call(String method,String route,Object body) throws Exception {
        var builder=HttpRequest.newBuilder(URI.create(base+route)).timeout(Duration.ofSeconds(12));
        if(body!=null)builder.header("Content-Type","application/json");
        var response=http.send(builder.method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build(),HttpResponse.BodyHandlers.ofString());
        return new Reply(response.statusCode(),response.body().isBlank()?NullNode.instance:json.readTree(response.body()),response.body());
    }
    private Reply auto(ObjectNode body)throws Exception{return call("POST","/api/evaluations/auto",body);}
    private Reply status(ObjectNode body)throws Exception{return call("GET","/api/evaluation-requests/"+body.get("request_id").asText(),null);}
    private int count(){return db().queryForObject("SELECT count(*) FROM evaluations",Integer.class);}
    private void safe(Reply reply){for(String s:List.of("PRIVATE_UPSTREAM_TEXT","PRIVATE_AUDIO",endpoint,temp.toString(),"SQLException"))assertFalse(reply.raw().contains(s));}
    @Test void successScoresPinsSavesAndReplaysWithoutInference()throws Exception{
        var body=payload();int before=count();var first=auto(body);assertEquals(200,first.code(),first.raw());
        assertEquals("model",first.body().path("origin").asText());assertEquals(100,first.body().at("/original_score/overall_score").asInt());
        assertEquals(first.body().get("original_score"),first.body().get("final_score"));assertEquals(before+1,count());
        assertEquals(fixture.get("conversation"),received.get("conversation"));assertEquals(fixture.get("checklist"),received.get("checklist"));
        assertTrue(received.findValues("audio_url").isEmpty());assertFalse(received.toString().contains("PRIVATE_AUDIO"));
        assertEquals(first.body(),auto(body).body());assertEquals(1,calls.get());
        assertEquals(Set.of("request_id","status","evaluation_id","error"),new HashSet<>(json.convertValue(status(body).body(),Map.class).keySet()));
        assertEquals("succeeded",status(body).body().path("status").asText());
        assertTrue(db().queryForObject("SELECT diagnostics_json FROM evaluation_requests WHERE request_id=?",String.class,body.path("request_id").asText()).contains("fake-http"));
        assertThrows(Exception.class,()->db().update("UPDATE evaluations SET origin='manual' WHERE id=?",first.body().path("id").asText()));
        assertEquals(first.body(),call("GET","/api/evaluations/"+first.body().path("id").asText(),null).body());
    }
    @ParameterizedTest @ValueSource(strings={"request_id","contract_version","conversation_id","checklist_key","checklist_version","missing_answer","duplicate_answer","evidence","message_id","empty_evidence","scale","na","unknown_field","numeric_string","zero_attempts","duplicate_json","invalid_utf8","huge","wrong_type","redirect","error_bad_echo"})
    void invalidOutputIsTerminalSafeAndNeverSaved(String scenario,CapturedOutput output)throws Exception{
        mode.set(scenario);var body=payload();int before=count();var reply=auto(body);assertEquals(502,reply.code(),reply.raw());
        assertEquals("EVALUATOR_INVALID_OUTPUT",reply.body().at("/detail/code").asText());assertEquals("failed",status(body).body().path("status").asText());
        assertEquals(before,count());assertEquals(reply.body(),auto(body).body());assertEquals(1,calls.get());safe(reply);
        assertFalse(output.getAll().contains("PRIVATE_UPSTREAM_TEXT"));
    }
    @ParameterizedTest @ValueSource(strings={"slow_headers","slow_body","drop"})
    void timeoutOrLostResponseIsUnknownAndCannotReplay(String scenario)throws Exception{
        mode.set(scenario);var body=payload();int before=count();var reply=auto(body);
        assertTrue(Set.of(502,504).contains(reply.code()),reply.raw());assertEquals("unknown",status(body).body().path("status").asText());
        assertEquals(before,count());assertEquals(reply.body(),auto(body).body());assertEquals(1,calls.get());
    }
    @Test void upstreamErrorIsValidatedAndSanitized()throws Exception{
        mode.set("error");var body=payload();var reply=auto(body);assertEquals(503,reply.code());safe(reply);
        assertEquals("EVALUATOR_BUSY",reply.body().at("/detail/code").asText());assertTrue(reply.body().at("/detail/retryable").asBoolean());
        assertEquals("failed",status(body).body().path("status").asText());assertEquals(reply.body(),auto(body).body());assertEquals(1,calls.get());
    }
    @Test void duplicatePendingAndConflictingIdDoNotCallAgainOrHoldSqlite()throws Exception{
        mode.set("block");var body=payload();var future=CompletableFuture.supplyAsync(()->{try{return auto(body);}catch(Exception e){throw new CompletionException(e);}});
        assertTrue(entered.await(5,TimeUnit.SECONDS));
        try{
            assertEquals("pending",status(body).body().path("status").asText());assertEquals(202,auto(body).code());
            var other=body.deepCopy().put("checklist_version",999);var conflict=auto(other);
            assertEquals(409,conflict.code());assertEquals("REQUEST_ID_CONFLICT",conflict.body().at("/detail/code").asText());
            var draft=(ObjectNode)fixture.get("checklist").deepCopy();draft.remove(List.of("key","version"));draft.put("title","Concurrent synthetic version");
            var latest=call("GET","/api/checklists/synthetic-local",null).body().get("version").asInt();
            assertEquals(200,call("PUT","/api/checklists/synthetic-local?expected_version="+latest,draft).code());
        }finally{release.countDown();}
        var result=future.get(5,TimeUnit.SECONDS);assertEquals(200,result.code(),result.raw());assertEquals(1,result.body().get("checklist_version").asInt());assertEquals(1,calls.get());
    }
    @Test void failedAtomicFinalizationRollsBackEvaluationAndLeavesUnknown()throws Exception{
        var body=payload();int before=count();db().execute("CREATE TRIGGER fail_auto_finish BEFORE UPDATE ON evaluation_requests WHEN NEW.status='succeeded' BEGIN SELECT RAISE(ABORT,'synthetic_failure'); END");
        try{assertEquals(502,auto(body).code());}finally{db().execute("DROP TRIGGER fail_auto_finish");}
        assertEquals(before,count());assertEquals("unknown",status(body).body().get("status").asText());assertEquals(502,auto(body).code());assertEquals(1,calls.get());
    }
    @Test void restartPreservesSuccessAndMarksInterruptedPendingUnknown()throws Exception{
        var success=payload();var saved=auto(success);assertEquals(200,saved.code());
        var pending=payload();var codec=app.getBean(ContractJson.class);var pinned=(ObjectNode)fixture.deepCopy();pinned.put("request_id",pending.get("request_id").asText());
        app.getBean(TransactionTemplate.class).executeWithoutResult(tx -> assertTrue(app.getBean(RequestLedger.class).claim(codec.read(jsonBytes(pending),AutoRequest.class),codec.readRequest(jsonBytes(pinned)))));
        app.close();boot();assertEquals(saved.body(),auto(success).body());assertEquals("unknown",status(pending).body().get("status").asText());
        assertEquals(504,auto(pending).code());assertEquals(1,calls.get());
        assertThrows(Exception.class,()->db().update("UPDATE evaluation_requests SET status='pending' WHERE request_id=?",pending.get("request_id").asText()));
    }
    private byte[] jsonBytes(JsonNode node){try{return json.writeValueAsBytes(node);}catch(Exception e){throw new AssertionError(e);}}
    @Test void syntheticGroupLabelAloneNeverAllowsInference()throws Exception{
        var source=(ObjectNode)fixture.get("conversation").deepCopy();source.put("id","SYNTHETIC:unapproved").put("conversation_id","unapproved");
        ((ObjectNode)source.at("/messages/0")).put("text","Own synthetic altered text, not an approved fixture");
        assertEquals(200,call("POST","/api/datasets/import",dataset(source)).code());var body=payload().put("conversation_id","SYNTHETIC:unapproved");
        var reply=auto(body);assertEquals(503,reply.code());assertEquals("PRIVACY_POLICY_UNCONFIGURED",reply.body().at("/detail/code").asText());
        assertEquals(0,calls.get());assertEquals(404,status(body).code());
    }
    @ParameterizedTest @ValueSource(strings={"text","speaker","timestamp","checklist"})
    void fullFixtureContentIsCheckedEvenWithIdenticalSourceIdentity(String part){
        var edited=fixture.deepCopy();
        if(part.equals("checklist"))((ObjectNode)edited.at("/checklist/criteria/0")).put("instruction","Altered synthetic instruction");
        else ((ObjectNode)edited.at("/conversation/messages/0")).put(part,part.equals("speaker")?"operator":part.equals("timestamp")?"00:02":"Altered synthetic text");
        var request=app.getBean(ContractJson.class).readRequest(jsonBytes(edited));
        assertThrows(MlFailure.class,()->app.getBean(SyntheticPolicy.class).requireApproved(request));assertEquals(0,calls.get());
    }
    @ParameterizedTest @ValueSource(strings={"en_public_na","en_protected_violation","ru_public_na","ru_protected_violation","kz_public_na","kz_protected_violation"})
    void allSixBundledFixturePairsAreApproved(String name)throws Exception{
        byte[] bytes=Files.readAllBytes(Path.of("../ml-service/tests/fixtures",name,"request.json"));
        assertDoesNotThrow(()->app.getBean(SyntheticPolicy.class).requireApproved(app.getBean(ContractJson.class).readRequest(bytes)));
    }
    @Test void missingAndInvalidStatusIdsDoNotCallPython()throws Exception{
        var body=payload();var reply=status(body);assertEquals(404,reply.code());assertEquals(body.get("request_id"),reply.body().at("/detail/request_id"));
        assertEquals(422,call("GET","/api/evaluation-requests/not-a-uuid",null).code());assertEquals(0,calls.get());
    }
}
