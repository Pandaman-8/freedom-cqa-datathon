package cqa.scoring;

import java.math.BigDecimal;
import java.util.List;

/** cqa-score/1 snapshot shape, matching the legacy calculate() result. */
public record ScoreResult(BigDecimal overall_score, BigDecimal applicable_weight, Integer max_score,
        boolean critical_violation, List<String> critical_criterion_ids,
        List<CriterionScore> criteria, List<SectionScore> sections) {
    public ScoreResult {
        critical_criterion_ids = List.copyOf(critical_criterion_ids);
        criteria = List.copyOf(criteria);
        sections = List.copyOf(sections);
    }
    public record CriterionScore(String criterion_id, String answer, BigDecimal value,
            BigDecimal configured_weight, BigDecimal effective_weight, BigDecimal earned_points,
            BigDecimal raw_points, boolean is_critical) {}
    public record SectionScore(String section_id, BigDecimal earned_points,
            BigDecimal applicable_weight, BigDecimal percent) {}
}
