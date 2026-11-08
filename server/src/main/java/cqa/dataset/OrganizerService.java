package cqa.dataset;

import com.fasterxml.jackson.annotation.JsonProperty;
import cqa.api.ApiFailure;
import cqa.api.RequestBodies;
import cqa.dto.*;
import cqa.service.ConversationService;
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import static cqa.dataset.OrganizerFailure.Reason.*;

@Service
public class OrganizerService {
    public record FetchRequest(@JsonProperty(required=true) @NotNull @Text(max=200) String group_id) {}
    private final OrganizerClient client;
    private final ContractJson json;
    private final ConversationService conversations;
    private final RequestBodies bodies;
    public OrganizerService(OrganizerClient client, ContractJson json, ConversationService conversations, RequestBodies bodies) {
        this.client = client; this.json = json; this.conversations = conversations;
        this.bodies = bodies;
    }
    public Dataset.ImportResult fetch(FetchRequest request) {
        json.validateShape(request);
        byte[] bytes = client.fetch(request.group_id()); // No database transaction while awaiting the organizer.
        try {
            var envelope = bodies.dataset(bytes);
            if (!envelope.data().dataset_group_id().equals(request.group_id())) throw new OrganizerFailure(GROUP_MISMATCH);
            return conversations.importDataset(envelope, bytes);
        } catch (ContractViolation e) {
            throw new OrganizerFailure(INVALID_RESPONSE);
        } catch (ApiFailure e) {
            if (e.status == 422) throw new OrganizerFailure(INVALID_RESPONSE);
            throw e; // Preserve T05's atomic changed-content409 without swallowing a storage fault.
        }
    }
}
