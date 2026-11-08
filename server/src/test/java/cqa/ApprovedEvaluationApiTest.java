package cqa;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class ApprovedEvaluationApiTest {
    @TempDir Path temp;
    final ObjectMapper json=new ObjectMapper();
    String base;
    JsonNode call(HttpClient client,String method,String route,JsonNode body,int expected) throws Exception {
        var req=HttpRequest.newBuilder(URI.create(base+route)).header("Content-Type","application/json")
                .method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofByteArray(json.writeValueAsBytes(body))).build();
        var response=client.send(req,HttpResponse.BodyHandlers.ofString());
        assertEquals(expected,response.statusCode());return json.readTree(response.body());
    }
    @Test void approvedV1ThenHotApprovedArbitraryV2UsePinnedLedgerAndScoring() throws Exception {
        var fixture=json.readTree(Path.of("../ml-service/tests/fixtures/en_public_na/request.json").toFile());
        var expected=json.readTree(Path.of("../ml-service/tests/fixtures/en_public_na/expected.json").toFile());
        var v1=(ObjectNode)fixture.get("checklist").deepCopy();var v2=v1.deepCopy();v2.put("version",2);
        ((ObjectNode)v2.at("/criteria/0")).put("id","NEW_APPROVED_ITEM").put("instruction","Reviewed test instruction, interpreted by a fixture stub only.");
        var dataset=json.createObjectNode().put("isSuccess",true).put("error","");
        var src=fixture.get("conversation");var data=dataset.putObject("data").put("dataset_group_id",src.get("dataset_group_id").asText()).put("total_records",1);
        var row=data.putArray("records").addObject().put("conversation_id",src.get("conversation_id").asText()).put("channel",src.get("channel").asText()).put("language",src.get("language").asText()).putNull("audio_url");
        var turns=row.putArray("transcript");for(var m:src.get("messages")){var turn=(ObjectNode)m.deepCopy();turn.remove("id");turns.add(turn);}
        Path input=temp.resolve("source.json"),approval=temp.resolve("test.ml-approval.json");byte[] bytes=json.writeValueAsBytes(dataset);Files.write(input,bytes);
        var calls=new AtomicInteger();var fake=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        fake.createContext("/health",e->{byte[] out="{\"configured\":true,\"ready\":true,\"reason\":null,\"contract_version\":\"2.0.0\"}".getBytes();e.getResponseHeaders().set("Content-Type","application/json");e.sendResponseHeaders(200,out.length);e.getResponseBody().write(out);e.close();});
        fake.createContext("/v1/evaluate",e->{
            calls.incrementAndGet();var request=json.readTree(e.getRequestBody());assertEquals(src,request.get("conversation"));
            assertEquals(request.at("/checklist/version").asInt()==1?v1:v2,request.get("checklist"));
            ObjectNode result=json.createObjectNode().put("contract_version","2.0.0").put("request_id",request.get("request_id").asText())
                .put("conversation_id",src.get("id").asText()).put("checklist_key",v1.get("key").asText()).set("checklist_version",request.at("/checklist/version"));
            var answers=expected.get("answers").deepCopy();((ObjectNode)answers.get(0)).put("criterion_id",request.at("/checklist/criteria/0/id").asText());
            result.set("answers",answers);var diagnostics=result.putObject("diagnostics").put("provider","local-test").put("model","fake-http").put("prompt_version","test-only")
                .put("attempt_count",1).putNull("input_tokens").putNull("output_tokens").putNull("estimated_cost_usd").put("latency_ms",1);diagnostics.putArray("warnings");
            byte[] out=json.writeValueAsBytes(result);e.getResponseHeaders().set("Content-Type","application/json");e.sendResponseHeaders(200,out.length);e.getResponseBody().write(out);e.close();
        });fake.start();String endpoint="http://127.0.0.1:"+fake.getAddress().getPort()+"/v1/evaluate";
        var grant=json.createObjectNode().put("approval_reference","TEST ONLY").put("processing_mode","local_only")
            .put("destination_description","Local fixture stub; no external network").put("expires_at",Instant.now().plusSeconds(300).toString())
            .put("ml_url",endpoint).put("dataset_path",input.toString()).put("dataset_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)));
        grant.putArray("approved_by").add("Farhat").add("Nurtas");grant.putArray("conversation_ids").add(src.get("id").asText());grant.putArray("checklist_snapshots").add(v1);
        Files.write(approval,json.writeValueAsBytes(grant));
        ServletWebServerApplicationContext app=null;
        try(var client=HttpClient.newHttpClient()){
            app=(ServletWebServerApplicationContext)new SpringApplicationBuilder(Application.class).run("--server.port=0","--cqa.db-path="+temp.resolve("test.sqlite"),
                "--cqa.ml-url="+endpoint,"--cqa.ml-data-mode=approved_dataset","--cqa.ml-approval-file="+approval,"--cqa.organizer-url=","--logging.level.root=WARN","--spring.main.banner-mode=off");
            base="http://127.0.0.1:"+app.getWebServer().getPort();call(client,"POST","/api/datasets/import",dataset,200);
            var draft=v1.deepCopy();draft.remove(List.of("key","version"));call(client,"POST","/api/checklists/synthetic-local",draft,200);
            var body=json.createObjectNode().put("request_id",UUID.randomUUID().toString()).put("conversation_id",src.get("id").asText()).put("checklist_key","synthetic-local").put("checklist_version",1);
            String status="/api/ai/status?conversation_id="+URLEncoder.encode(src.get("id").asText(),java.nio.charset.StandardCharsets.UTF_8)+"&checklist_key=synthetic-local&checklist_version=";
            assertTrue(call(client,"GET",status+"1",null,200).get("ready").asBoolean());assertEquals(0,calls.get());
            var first=call(client,"POST","/api/evaluations/auto",body,200);assertEquals(100,first.at("/original_score/overall_score").asInt());
            assertEquals(first,call(client,"POST","/api/evaluations/auto",body,200));assertEquals(1,calls.get());
            draft=v2.deepCopy();draft.remove(List.of("key","version"));call(client,"PUT","/api/checklists/synthetic-local?expected_version=1",draft,200);
            body.put("request_id",UUID.randomUUID().toString()).put("checklist_version",2);
            assertFalse(call(client,"GET",status+"2",null,200).get("selection_allowed").asBoolean());
            assertEquals("PRIVACY_POLICY_UNCONFIGURED",call(client,"POST","/api/evaluations/auto",body,503).at("/detail/code").asText());assertEquals(1,calls.get());
            ((ArrayNode)grant.get("checklist_snapshots")).add(v2);Files.write(approval,json.writeValueAsBytes(grant));
            assertTrue(call(client,"GET",status+"2",null,200).get("ready").asBoolean());
            var second=call(client,"POST","/api/evaluations/auto",body,200);assertEquals(2,second.get("checklist_version").asInt());assertEquals("model",second.get("origin").asText());assertEquals(2,calls.get());
            assertEquals(first,call(client,"GET","/api/evaluations/"+first.get("id").asText(),null,200));
            Files.delete(approval);body.put("request_id",UUID.randomUUID().toString());call(client,"POST","/api/evaluations/auto",body,503);assertEquals(2,calls.get());
        }finally{if(app!=null)app.close();fake.stop(0);}
    }
}
