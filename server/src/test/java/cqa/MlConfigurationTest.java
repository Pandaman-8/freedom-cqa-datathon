package cqa;

import cqa.dto.ContractJson;
import cqa.ml.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import static org.junit.jupiter.api.Assertions.*;

class MlConfigurationTest {
    @ParameterizedTest
    @ValueSource(strings={"", "relative/path", "//127.0.0.1:8001/v1/evaluate", "https://example.invalid/v1/evaluate",
        "http://localhost:8001/v1/evaluate", "http://127.0.0.1/v1/evaluate", "http://127.0.0.1:0/v1/evaluate",
        "http://127.0.0.1:8001/other", "http://user:password@127.0.0.1:8001/v1/evaluate",
        "http://127.0.0.1:8001/v1/evaluate?secret=value", "http://127.0.0.1:8001/v1/evaluate#fragment"})
    void onlyExplicitCredentialFreeLoopbackRouteIsPermitted(String url){
        try(var json=new ContractJson();var client=new MlClient(json,url,3000,70000)){
            var error=assertThrows(MlFailure.class,client::endpoint);
            assertEquals(501,error.status);assertEquals("EVALUATOR_UNCONFIGURED",error.code);
            assertFalse(error.getMessage().contains("password"));assertFalse(error.getMessage().contains("secret"));
        }
    }
    @Test void configuredDefaultRouteNeedsNoNetworkOrCredentials(){
        try(var json=new ContractJson();var client=new MlClient(json,"http://127.0.0.1:8001/v1/evaluate",3000,70000)){
            assertEquals("/v1/evaluate",client.endpoint().getPath());
        }
    }
}
