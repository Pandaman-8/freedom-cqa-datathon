package cqa.scoring;

import cqa.dto.*;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;
import static cqa.scoring.ScoreResult.*;

/** Pure deterministic scoring. No storage, HTTP, inference, clock or mutable state. */
public final class ScoringEngine {
    public static final String VERSION = "cqa-score/1";

    public ScoreResult calculate(Checklist checklist, List<CriterionAnswer> answers) {
        ContractValidation.answers(checklist, answers);
        Map<String, CriterionAnswer> byId = answers.stream()
            .collect(Collectors.toMap(CriterionAnswer::criterion_id, Function.identity()));
        BigDecimal totalWeight = checklist.criteria().stream()
            .filter(c -> !byId.get(c.id()).answer().equals("na"))
            .map(Criterion::weight).reduce(BigDecimal.ZERO, BigDecimal::add);
        ExactDecimal totalEarned = ExactDecimal.ZERO;
        Map<String, ExactDecimal> earned = new LinkedHashMap<>();
        Map<String, BigDecimal> weights = new LinkedHashMap<>();
        for (Section section : checklist.sections()) {
            earned.put(section.id(), ExactDecimal.ZERO);
            weights.put(section.id(), BigDecimal.ZERO);
        }
        List<String> criticalIds = new ArrayList<>();
        List<CriterionScore> rows = new ArrayList<>();
        for (Criterion criterion : checklist.criteria()) {
            CriterionAnswer answer = byId.get(criterion.id());
            boolean critical = criterion.kind().equals("flag") && answer.answer().equals("yes");
            if (critical) criticalIds.add(criterion.id());
            ExactDecimal raw = null;
            if (criterion.weight().signum() > 0 && !answer.answer().equals("na")) {
                raw = switch (answer.answer()) {
                    case "yes" -> ExactDecimal.of(criterion.weight());
                    case "no" -> ExactDecimal.ZERO;
                    case "scale" -> new ExactDecimal(criterion.weight().multiply(answer.value()),
                        criterion.levels().stream().map(ScaleLevel::value).max(BigDecimal::compareTo).orElseThrow());
                    default -> throw new IllegalStateException("validated_answer_required");
                };
                totalEarned = totalEarned.add(raw);
                earned.put(criterion.section_id(), earned.get(criterion.section_id()).add(raw));
                weights.merge(criterion.section_id(), criterion.weight(), BigDecimal::add);
            }
            rows.add(new CriterionScore(criterion.id(), answer.answer(), answer.value(), criterion.weight(),
                raw == null ? null : ExactDecimal.of(criterion.weight()).percentOf(totalWeight).rounded(),
                raw == null ? null : raw.percentOf(totalWeight).rounded(),
                raw == null ? null : raw.rounded(), critical));
        }
        List<SectionScore> sections = new ArrayList<>();
        for (Section section : checklist.sections()) {
            BigDecimal weight = weights.get(section.id());
            ExactDecimal points = earned.get(section.id());
            sections.add(new SectionScore(section.id(), points.rounded(), rounded(weight),
                weight.signum() == 0 ? null : points.percentOf(weight).rounded()));
        }
        return new ScoreResult(totalWeight.signum() == 0 ? null : totalEarned.percentOf(totalWeight).rounded(),
            rounded(totalWeight), totalWeight.signum() == 0 ? null : 100, !criticalIds.isEmpty(), criticalIds, rows, sections);
    }
    private static BigDecimal rounded(BigDecimal value) { return value.setScale(2, RoundingMode.HALF_UP); }
}
