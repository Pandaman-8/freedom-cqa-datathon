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
            .put("processing_mode","local_only").put("destination_description","local test stub, no external network")
            .put("expires_at",Instant.now().plusSeconds(3600).toString()).put("ml_url",endpoint)
            .put("dataset_path",dataset.toString()).put("dataset_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)));
        grant.putArray("approved_by").add("Farhat").add("Nurtas");
        grant.putArray("conversation_ids").add(source.get("id").asText());
        grant.putArray("checklist_snapshots").add(fixture.get("checklist").deepCopy());
        file=temp.resolve("test.ml-approval.json");
    }
    @AfterEach void close(){json.close();}
    SyntheticPolicy policy() throws Exception {
        Files.write(file,mapper.writeValueAsBytes(grant));
        return new SyntheticPolicy(json,"approved_dataset",file.toString(),endpoint);
    }
    EvaluationRequest request(ObjectNode input) throws Exception {return json.readRequest(mapper.writeValueAsBytes(input));}
    void rejected(SyntheticPolicy policy, ObjectNode input) throws Exception {
        var request=request(input);
        var error=assertThrows(MlFailure.class,()->policy.requireApproved(request));
        assertEquals("PRIVACY_POLICY_UNCONFIGURED",error.code);
    }
    @Test void explicitSnapshotAdmitsExistingSourceButNotOtherVersionOrContent() throws Exception {
        var policy=policy();policy.requireApproved(request(fixture));
        var changed=fixture.deepCopy();((ObjectNode)changed.get("checklist")).put("version",2);
        rejected(policy,changed);
        changed=fixture.deepCopy();((ObjectNode)changed.at("/conversation/messages/0")).put("text","Altered test source");
        rejected(policy,changed);
        changed=fixture.deepCopy();((ObjectNode)changed.at("/checklist/criteria/0")).put("instruction","Different instruction");
        rejected(policy,changed);
    }
    @Test void arbitraryCriterionAndVersionNeedOnlyNewPrivateApprovalNotSourceEdits() throws Exception {
        var changed=fixture.deepCopy();((ObjectNode)changed.get("checklist")).put("version",2);
        ((ObjectNode)changed.at("/checklist/criteria/0")).put("id","NEW_REVIEWED_CRITERION").put("instruction","Check the reviewed new instruction.");
        var policy=policy(); rejected(policy,changed);
        ((ArrayNode)grant.get("checklist_snapshots")).add(changed.get("checklist"));
        Files.write(file,mapper.writeValueAsBytes(grant));
        policy.requireApproved(request(fixture));policy.requireApproved(request(changed));
    }
    @Test void deletingOrEditingApprovalRevokesWithoutRestart() throws Exception {
        var policy=policy();Files.writeString(file,"{}");rejected(policy,fixture);
        policy=policy();Files.delete(file);rejected(policy,fixture);
    }
    @ParameterizedTest @ValueSource(strings={"hash","expiry","destination","reviewer","scope","rubric","path","mode","extra","no-reference"})
    void malformedOrUnagreedApprovalNeverFallsBackToSynthetic(String kind) throws Exception {
        switch(kind){
            case "hash" -> grant.put("dataset_sha256","0".repeat(64));
            case "expiry" -> grant.put("expires_at","2000-01-01T00:00:00Z");
            case "destination" -> grant.put("ml_url","http://127.0.0.1:9000/v1/evaluate");
            case "reviewer" -> grant.putArray("approved_by").add("Farhat");
            case "scope" -> grant.putArray("conversation_ids").add("NOT_IN_REVIEWED_DATASET");
            case "rubric" -> grant.putArray("checklist_snapshots");
            case "path" -> grant.put("dataset_path","relative.json");
            case "mode" -> grant.put("processing_mode","DEV");
            case "extra" -> grant.put("disable_checks",true);
            case "no-reference" -> grant.put("approval_reference","");
        }
        rejected(policy(),fixture);
    }
    @Test void unknownDataModeAndMissingApprovalFailClosed() throws Exception {
        rejected(new SyntheticPolicy(json,"DEV","",endpoint),fixture);
        rejected(new SyntheticPolicy(json,"approved_dataset","",endpoint),fixture);
    }
    @Test void defaultSyntheticPolicyStillPinsFullChecklist() throws Exception {
        var policy=new SyntheticPolicy(json,"synthetic_only","",endpoint);policy.requireApproved(request(fixture));
        var changed=fixture.deepCopy();((ObjectNode)changed.get("checklist")).put("version",2);rejected(policy,changed);
    }
}
