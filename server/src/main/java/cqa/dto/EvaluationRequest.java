package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record EvaluationRequest(
    @JsonProperty(value="contract_version", required=true) @NotNull @Pattern(regexp="2\\.0\\.0") String contract_version,
    @JsonProperty(value="request_id", required=true) @NotNull @Pattern(regexp=ContractJson.UUID_PATTERN) String request_id,
    @JsonProperty(value="conversation", required=true) @NotNull @Valid SourceConversation conversation,
    @JsonProperty(value="checklist", required=true) @NotNull @Valid Checklist checklist
) {
}
