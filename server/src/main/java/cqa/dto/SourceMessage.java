package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.*;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record SourceMessage(
    @JsonProperty(value="id", required=true) @NotNull @Pattern(regexp="m[0-9]{4,}") String id,
    @JsonProperty(value="timestamp", required=true) @NotNull @Text String timestamp,
    @JsonProperty(value="speaker", required=true) @NotNull @Pattern(regexp="operator|client|bot|system") String speaker,
    @JsonProperty(value="text", required=true) @NotNull String text
) {
}
