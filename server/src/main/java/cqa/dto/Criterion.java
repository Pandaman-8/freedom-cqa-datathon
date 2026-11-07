package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.List;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record Criterion(
    @JsonProperty(value="id", required=true) @NotNull @Text(max=40) String id,
    @JsonProperty(value="section_id", required=true) @NotNull @Text String section_id,
    @JsonProperty(value="title", required=true) @NotNull @Text String title,
    @JsonProperty(value="instruction", required=true) @NotNull @Text String instruction,
    @JsonProperty(value="kind", required=true) @NotNull @Pattern(regexp="binary|scale|flag") String kind,
    @JsonProperty(value="weight", required=true) @NotNull @DecimalMin("0") @DecimalMax("100") BigDecimal weight,
    @JsonProperty(value="allow_na", required=true) @NotNull Boolean allow_na,
    @JsonProperty(value="na_rule", required=true) String na_rule,
    @JsonProperty(value="levels", required=true) @NotNull @Size(min=0) List<@NotNull @Valid ScaleLevel> levels
) {
    public Criterion {
        levels = levels == null ? null : List.copyOf(levels);
    }
}
