package cqa.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigInteger;
import java.util.List;

/** Immutable contract 2.0.0 value; wire names are intentionally unchanged. */
public record Checklist(
    @JsonProperty(value="key", required=true) @NotNull @Text(max=80) String key,
    @JsonProperty(value="version", required=true) @NotNull @DecimalMin("1") BigInteger version,
    @JsonProperty(value="title", required=true) @NotNull @Text String title,
    @JsonProperty(value="description", required=true) @NotNull String description,
    @JsonProperty(value="sections", required=true) @NotNull @Size(min=1) List<@NotNull @Valid Section> sections,
    @JsonProperty(value="criteria", required=true) @NotNull @Size(min=1, max=100) List<@NotNull @Valid Criterion> criteria
) {
    public Checklist {
        sections = sections == null ? null : List.copyOf(sections);
        criteria = criteria == null ? null : List.copyOf(criteria);
    }
}
