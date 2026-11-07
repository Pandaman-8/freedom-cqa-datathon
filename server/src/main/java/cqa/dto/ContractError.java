package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record ContractError(
    @JsonProperty(value="detail", required=true) @NotNull @Valid ErrorDetail detail
) {
}
