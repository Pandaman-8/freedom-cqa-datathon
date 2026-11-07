package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.*;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record Evidence(
    @JsonProperty(value="message_id", required=true) @NotNull @Pattern(regexp="m[0-9]{4,}") String message_id,
    @JsonProperty(value="quote", required=true) @NotNull @Text String quote
) {
}
