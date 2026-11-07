package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record ScaleLevel(
    @JsonProperty(value="value", required=true) @NotNull @DecimalMin("0") BigDecimal value,
    @JsonProperty(value="description", required=true) @NotNull @Text String description
) {
}
