package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.List;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record CriterionAnswer(
    @JsonProperty(value="criterion_id", required=true) @NotNull @Text(max=40, nonblank=false) String criterion_id,
    @JsonProperty(value="answer", required=true) @NotNull @Pattern(regexp="yes|no|na|scale") String answer,
    @JsonProperty(value="value", required=true) BigDecimal value,
    @JsonProperty(value="explanation", required=true) @NotNull @Text String explanation,
    @JsonProperty(value="evidence", required=true) @NotNull @Size(min=1) List<@NotNull @Valid Evidence> evidence
) {
    public CriterionAnswer {
        evidence = evidence == null ? null : List.copyOf(evidence);
    }
    @AssertTrue @JsonIgnore
    public boolean isValueConsistent() {
        return "scale".equals(answer) ? value != null && value.signum() >= 0 : value == null;
    }
}
