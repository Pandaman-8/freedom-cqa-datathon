package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.*;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record ErrorDetail(
    @JsonProperty(value="code", required=true) @NotNull @Text String code,
    @JsonProperty(value="message", required=true) @NotNull @Text String message,
    @JsonProperty(value="retryable", required=true) @NotNull Boolean retryable,
    @JsonProperty(value="request_id", required=true) @Pattern(regexp=ContractJson.UUID_PATTERN) String request_id
) {
}
