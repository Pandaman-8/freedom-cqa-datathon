package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigInteger;
import java.util.List;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record EvaluationResult(
    @JsonProperty(value="contract_version", required=true) @NotNull @Pattern(regexp="2\\.0\\.0") String contract_version,
    @JsonProperty(value="request_id", required=true) @NotNull @Pattern(regexp=ContractJson.UUID_PATTERN) String request_id,
    @JsonProperty(value="conversation_id", required=true) @NotNull @Text String conversation_id,
    @JsonProperty(value="checklist_key", required=true) @NotNull @Text(max=80, nonblank=false) String checklist_key,
    @JsonProperty(value="checklist_version", required=true) @NotNull @DecimalMin("1") BigInteger checklist_version,
    @JsonProperty(value="answers", required=true) @NotNull @Size(min=1, max=100) List<@NotNull @Valid CriterionAnswer> answers,
    @JsonProperty(value="diagnostics", required=true) @NotNull @Valid Diagnostics diagnostics
) {
    public EvaluationResult {
        answers = answers == null ? null : List.copyOf(answers);
    }
}
