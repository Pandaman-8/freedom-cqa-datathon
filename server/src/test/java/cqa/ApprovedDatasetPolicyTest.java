package cqa;

import cqa.dto.*;
import cqa.ml.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ApprovedDatasetPolicyTest {
    @TempDir Path temp;
    final ObjectMapper mapper=new ObjectMapper();
    ContractJson json;
    ObjectNode fixture, grant;
    Path file;
    final String endpoint="http://127.0.0.1:8001/v1/evaluate";
    @BeforeEach void setup() throws Exception {
        json=new ContractJson();
        fixture=(ObjectNode)mapper.readTree(Path.of("../ml-service/tests/fixtures/en_public_na/request.json").toFile());
        var source=fixture.get("conversation");
        var envelope=mapper.createObjectNode().put("error","").put("isSuccess",true);
        var data=envelope.putObject("data").put("dataset_group_id",source.get("dataset_group_id").asText()).put("total_records",1);
        var record=data.putArray("records").addObject().put("conversation_id",source.get("conversation_id").asText())
            .put("channel",source.get("channel").asText()).put("language",source.get("language").asText()).putNull("audio_url");
        var turns=record.putArray("transcript");
        for(var message:source.get("messages")){var turn=(ObjectNode)message.deepCopy();turn.remove("id");turns.add(turn);}
        byte[] bytes=mapper.writeValueAsBytes(envelope);Path dataset=temp.resolve("source.json");Files.write(dataset,bytes);
        grant=mapper.createObjectNode().put("approval_reference","TEST ONLY — no live permission")
            .put("approval_version",2).put("session_id","test-session").put("provider","groq").put("model","openai/gpt-oss-20b").put("processing_mode","external_approved").put("destination_description","local test stub, no external network")
            .put("expires_at",Instant.now().plusSeconds(3600).toString()).put("ml_url",endpoint)
            .put("dataset_path",dataset.toString()).put("dataset_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)));
        grant.putArray("approved_by").add("Farhat").add("Nurtas");
        grant.putArray("conversation_ids").add(source.get("id").asText());
        grant.putObject("checklist_scope").put("key",fixture.at("/checklist/key").asText()).put("min_version",1).put("max_version",2).put("max_criteria",100).put("require_confirmation",true);
        file=temp.resolve("test.ml-approval.json");
    }
    @AfterEach void close(){json.close();}
    SyntheticPolicy policy() throws Exception {
        Files.write(file,mapper.writeValueAsBytes(grant));
        return new SyntheticPolicy(json,"approved_dataset",file.toString(),endpoint,true);
    }
    EvaluationRequest request(ObjectNode input) throws Exception {return json.readRequest(mapper.writeValueAsBytes(input));}
    void rejected(SyntheticPolicy policy, ObjectNode input) throws Exception {
        var request=request(input);
        var error=assertThrows(MlFailure.class,()->policy.requireApproved(request));
        assertEquals("PRIVACY_POLICY_UNCONFIGURED",error.code);
    }
    @Test void dynamicVersionsWithinScopeNeedNoGrantEditsButSourcesRemainExact() throws Exception {
        var policy=policy();policy.requireApproved(request(fixture));
        byte[] originalGrant=Files.readAllBytes(file);
        var changed=fixture.deepCopy();((ObjectNode)changed.get("checklist")).put("version",2);
        ((ObjectNode)changed.at("/checklist/criteria/0")).put("id","NEW_REVIEWED_CRITERION").put("instruction","Check a new instruction, no fixed response.");
        policy.requireApproved(request(changed));assertArrayEquals(originalGrant,Files.readAllBytes(file));
        ((ObjectNode)changed.get("checklist")).put("version",3);rejected(policy,changed);
        changed=fixture.deepCopy();((ObjectNode)changed.at("/conversation/messages/0")).put("text","Altered test source");rejected(policy,changed);
        changed=fixture.deepCopy();((ObjectNode)changed.get("checklist")).put("key","another-key");rejected(policy,changed);
    }
    @Test void disabledExternalOptInAndChangedDatasetFailClosed() throws Exception {
        policy();rejected(new SyntheticPolicy(json,"approved_dataset",file.toString(),endpoint,false),fixture);
        var policy=policy();Files.writeString(Path.of(grant.get("dataset_path").asText()),"{}");rejected(policy,fixture);
    }
    @Test void excessCriteriaAndVoiceSelectionAreNeverPermitted() throws Exception {
        ((ObjectNode)grant.get("checklist_scope")).put("max_criteria",1);rejected(policy(),fixture);
        var path=Path.of(grant.get("dataset_path").asText());var data=(ObjectNode)mapper.readTree(path.toFile());
        ((ObjectNode)data.at("/data/records/0")).put("channel","voice call");
        byte[] bytes=mapper.writeValueAsBytes(data);Files.write(path,bytes);
        grant.put("dataset_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)));
        rejected(policy(),fixture);
    }
    @Test void deletingOrEditingApprovalRevokesWithoutRestart() throws Exception {
        var policy=policy();Files.writeString(file,"{}");rejected(policy,fixture);
        policy=policy();Files.delete(file);rejected(policy,fixture);
    }
    @ParameterizedTest @ValueSource(strings={"hash","expiry","destination","reviewer","scope","rubric","path","mode","extra","no-reference","legacy","provider","model","session","scope-bounds","no-confirmation"})
    void malformedOrUnagreedApprovalNeverFallsBackToSynthetic(String kind) throws Exception {
        switch(kind){
            case "hash" -> grant.put("dataset_sha256","0".repeat(64));
            case "expiry" -> grant.put("expires_at","2000-01-01T00:00:00Z");
            case "destination" -> grant.put("ml_url","http://127.0.0.1:9000/v1/evaluate");
            case "reviewer" -> grant.putArray("approved_by").add("Farhat");
            case "scope" -> grant.putArray("conversation_ids").add("NOT_IN_REVIEWED_DATASET");
            case "rubric" -> grant.putNull("checklist_scope");
            case "path" -> grant.put("dataset_path","relative.json");
            case "mode" -> grant.put("processing_mode","DEV");
            case "extra" -> grant.put("disable_checks",true);
            case "no-reference" -> grant.put("approval_reference","");
            case "legacy" -> {grant.remove("checklist_scope");grant.putArray("checklist_snapshots").add(fixture.get("checklist"));}
            case "provider" -> grant.put("provider","other");
            case "model" -> grant.put("model","openai/gpt-oss-120b");
            case "session" -> grant.put("session_id","");
            case "scope-bounds" -> ((ObjectNode)grant.get("checklist_scope")).put("min_version",3);
            case "no-confirmation" -> ((ObjectNode)grant.get("checklist_scope")).put("require_confirmation",false);
        }
        rejected(policy(),fixture);
    }
    @Test void unknownDataModeAndMissingApprovalFailClosed() throws Exception {
        rejected(new SyntheticPolicy(json,"DEV","",endpoint,true),fixture);
        rejected(new SyntheticPolicy(json,"approved_dataset","",endpoint,true),fixture);
    }
    @Test void defaultSyntheticPolicyStillPinsFullChecklist() throws Exception {
        var policy=new SyntheticPolicy(json,"synthetic_only","",endpoint,false);policy.requireApproved(request(fixture));
        var changed=fixture.deepCopy();((ObjectNode)changed.get("checklist")).put("version",2);rejected(policy,changed);
    }
}
