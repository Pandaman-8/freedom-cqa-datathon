package cqa.api;

import com.fasterxml.jackson.annotation.JsonProperty;
import cqa.dto.*;
import cqa.scoring.ScoreResult;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigInteger;
import java.util.List;

public final class ApiModels {
    private ApiModels() {}
    public record ChecklistDraft(
        @JsonProperty(required=true) @NotNull @Text String title,
        @JsonProperty(required=true) @NotNull String description,
        @JsonProperty(required=true) @NotNull @Size(min=1) List<@NotNull @Valid Section> sections,
        @JsonProperty(required=true) @NotNull @Size(min=1,max=100) List<@NotNull @Valid Criterion> criteria) {
        public ChecklistDraft { sections = sections == null ? null : List.copyOf(sections); criteria = criteria == null ? null : List.copyOf(criteria); }
        public Checklist versioned(String key, BigInteger version) { return new Checklist(key, version, title, description, sections, criteria); }
    }
    public record ManualRequest(
        @JsonProperty(required=true) @NotNull @Text String conversation_id,
        @JsonProperty(required=true) @NotNull @Text(max=80) String checklist_key,
        @JsonProperty(required=true) @NotNull @DecimalMin("1") BigInteger checklist_version,
        @JsonProperty(required=true) @NotNull @Size(min=1,max=100) List<@NotNull @Valid CriterionAnswer> answers) {
        public ManualRequest { answers = answers == null ? null : List.copyOf(answers); }
    }
    public record AutoRequest(
        @JsonProperty(required=true) @NotNull @Pattern(regexp=ContractJson.UUID_PATTERN) String request_id,
        @JsonProperty(required=true) @NotNull @Text String conversation_id,
        @JsonProperty(required=true) @NotNull @Text(max=80) String checklist_key,
        @JsonProperty(required=true) @NotNull @DecimalMin("1") BigInteger checklist_version) {}

    public record EvaluationView(String id, String conversation_id, String checklist_key, BigInteger checklist_version,
        String origin, String created_at, List<CriterionAnswer> original_answers, ScoreResult original_score,
        List<CriterionAnswer> final_answers, ScoreResult final_score, List<Object> appeals, String review_status,
        String contract_version, String scoring_version) {}
}
