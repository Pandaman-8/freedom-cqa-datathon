package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.*;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record Section(
    @JsonProperty(value="id", required=true) @NotNull @Text(max=40) String id,
    @JsonProperty(value="title", required=true) @NotNull @Text(max=180) String title
) {
}
