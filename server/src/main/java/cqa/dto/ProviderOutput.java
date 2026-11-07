package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record ProviderOutput(
    @JsonProperty(value="answers", required=true) @NotNull @Size(min=1, max=100) List<@NotNull @Valid CriterionAnswer> answers
) {
    public ProviderOutput {
        answers = answers == null ? null : List.copyOf(answers);
    }
}
