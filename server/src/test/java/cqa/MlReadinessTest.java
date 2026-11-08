package cqa;
import cqa.dto.ContractJson;
import cqa.ml.MlClient;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;

class MlReadinessTest {
    @Test void probesOnlyHealthAndDoesNotTreatMalformedOrWrongVersionAsReady() throws Exception {
        var body=new AtomicReference<>("{\"configured\":true,\"ready\":true,\"reason\":null,\"model\":\"test\",\"contract_version\":\"2.0.0\"}");
        var status=new AtomicInteger(200);var gets=new AtomicInteger();var posts=new AtomicInteger();
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/health",e->{
            assertEquals("GET",e.getRequestMethod());assertEquals(0,e.getRequestBody().readAllBytes().length);gets.incrementAndGet();
            byte[] bytes=body.get().getBytes(StandardCharsets.UTF_8);e.getResponseHeaders().set("Content-Type","application/json");
            e.sendResponseHeaders(status.get(),bytes.length);e.getResponseBody().write(bytes);e.close();
        });
        server.createContext("/v1/evaluate",e->{posts.incrementAndGet();e.sendResponseHeaders(500,-1);e.close();});server.start();
        try(var json=new ContractJson();var client=new MlClient(json,"http://127.0.0.1:"+server.getAddress().getPort()+"/v1/evaluate",500,1000)) {
            assertTrue(client.health().ready());
            status.set(503);assertFalse(client.health().ready());
            status.set(200);body.set("{\"configured\":true,\"ready\":true,\"reason\":null,\"contract_version\":\"1.0.0\"}");assertFalse(client.health().ready());
            body.set("{\"configured\":\"true\",\"ready\":true,\"contract_version\":\"2.0.0\"}");assertFalse(client.health().ready());
            body.set("PRIVATE_ERROR_TEXT");var health=client.health();assertFalse(health.ready());assertFalse(health.toString().contains("PRIVATE_ERROR_TEXT"));
            assertEquals(5,gets.get());assertEquals(0,posts.get());
        }finally{server.stop(0);}
    }
    @Test void missingEndpointIsNotReadyAndNeedsNoNetwork(){
        try(var json=new ContractJson();var client=new MlClient(json,"",500,1000)){
            var health=client.health();assertFalse(health.configured());assertFalse(health.reachable());assertFalse(health.ready());
        }
    }
}
