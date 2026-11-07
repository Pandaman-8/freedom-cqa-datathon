package cqa.review;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import cqa.dto.CriterionAnswer;
import cqa.dto.Text;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

/** Java domain API only; the ML wire DTOs remain unchanged. */
public final class ReviewModels {
    private ReviewModels() {}
    public record AppealRequest(
        @JsonProperty(required=true) @NotNull @Text(max=40, nonblank=false) String criterion_id,
        @JsonProperty(required=true) @NotNull @Text(max=3000) String comment) {}

    public record Resolution(
        @JsonProperty(required=true) @NotNull @Pattern(regexp="confirm|change") String decision,
        @JsonProperty(required=true) @NotNull @Text(max=3000) String reason,
        @JsonProperty(required=true) @Valid CriterionAnswer replacement) {
        @AssertTrue @JsonIgnore public boolean isReplacementConsistent() {
            return "change".equals(decision) ? replacement != null : replacement == null;
        }
    }

    public record AppealView(String id, String evaluation_id, String criterion_id, String comment,
        String status, String decision, String reason, CriterionAnswer replacement,
        String created_at, String resolved_at, long created_revision, Long resolved_revision) {}
}
