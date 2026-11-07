package cqa.scoring;

import cqa.dto.*;
import com.fasterxml.jackson.databind.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import java.math.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.*;
import static org.junit.jupiter.api.Assertions.*;

class ScoringEngineTest {
    static ContractJson codec;
    static Checklist seed;
    static final ScoringEngine ENGINE = new ScoringEngine();
    static final ObjectMapper JSON = new ObjectMapper();
    static final Path ROOT = Path.of("..").toAbsolutePath().normalize();
    @BeforeAll static void setup() throws Exception {
        codec = new ContractJson();
        seed = codec.read(Files.readAllBytes(ROOT.resolve("backend/app/seed/chat_quality.json")), Checklist.class);
    }
    @AfterAll static void close() { codec.close(); }

    static Stream<String> references() throws Exception {
        List<String> lines = Files.readAllLines(Path.of("src/test/resources/scoring/seed-reference.tsv"));
        assertEquals(5185, lines.size());
        return lines.stream().skip(1);
    }

    @ParameterizedTest(name="Fraction/Python reference {index}") @MethodSource("references")
    void all5184CombinationsMatchEveryReferenceField(String reference) throws Exception {
        String[] parts = reference.split("\t");
        int ordinal = Integer.parseInt(parts[0]);
        List<CriterionAnswer> answers = new ArrayList<>();
        for (int i = seed.criteria().size() - 1; i >= 0; i--) {
            Criterion c = seed.criteria().get(i);
            List<CriterionAnswer> choices = choices(c);
            answers.addFirst(choices.get(ordinal % choices.size()));
            ordinal /= choices.size();
        }
        ScoreResult score = ENGINE.calculate(seed, answers);
        String canonical = JSON.writeValueAsString(canonical(JSON.valueToTree(score)));
        String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical.getBytes(StandardCharsets.UTF_8)));
        assertEquals(parts[1], hash, () -> "All-field mismatch: " + reference + " " + canonical);
    }

    private static Object canonical(JsonNode n) {
        if (n.isNumber()) return n.decimalValue().setScale(2, RoundingMode.UNNECESSARY).toPlainString();
        if (n.isObject()) {
            Map<String, Object> result = new TreeMap<>();
            n.properties().forEach(e -> result.put(e.getKey(), canonical(e.getValue())));
            return result;
        }
        if (n.isArray()) {
            List<Object> result = new ArrayList<>(); n.forEach(v -> result.add(canonical(v))); return result;
        }
        if (n.isNull()) return null;
        return n.isBoolean() ? n.booleanValue() : n.textValue();
    }

    private static List<CriterionAnswer> choices(Criterion c) {
        List<CriterionAnswer> result = new ArrayList<>();
        if (c.kind().equals("scale")) for (ScaleLevel l : c.levels()) result.add(answer(c.id(), "scale", l.value()));
        else { result.add(answer(c.id(), "yes", null)); result.add(answer(c.id(), "no", null)); }
        if (c.allow_na()) result.add(answer(c.id(), "na", null));
        return result;
    }
    static CriterionAnswer answer(String id, String kind, BigDecimal value) {
        return new CriterionAnswer(id, kind, value, "Synthetic reference.", List.of(new Evidence("m0001", "Synthetic")));
    }
    static Criterion scale(String id, String weight, boolean na, String... values) {
        return new Criterion(id, "s", "Custom", "Custom instruction", "scale", new BigDecimal(weight), na,
            na ? "Not applicable in this context" : null,
            Arrays.stream(values).map(v -> new ScaleLevel(new BigDecimal(v), "Configured level")).toList());
    }
    static Checklist custom(Criterion... criteria) {
        return new Checklist("custom", BigInteger.ONE, "Custom", "", List.of(new Section("s", "Section"),
            new Section("empty", "Empty")), List.of(criteria));
    }
    static void decimal(String expected, BigDecimal actual) {
        assertNotNull(actual); assertEquals(0, new BigDecimal(expected).compareTo(actual));
    }

    @Test void customScalesAndDecimalWeightsKeepUnroundedSums() {
        Checklist checklist = custom(scale("a", "0.01", false, "0", "1", "3"), scale("b", "0.02", false, "0", "1", "3"));
        ScoreResult result = ENGINE.calculate(checklist, List.of(answer("a", "scale", BigDecimal.ONE), answer("b", "scale", BigDecimal.ONE)));
        decimal("33.33", result.overall_score());
        decimal("0.01", result.sections().getFirst().earned_points());
        decimal("0.00", result.criteria().getFirst().raw_points());
        decimal("0.01", result.criteria().getLast().raw_points());
        assertNull(result.sections().getLast().percent());
    }
    @Test void exactRepeatingFractionsAcrossDifferentDenominators() {
        var checklist = custom(scale("a", "3", false, "0", "1", "3"), scale("b", "7", false, "0", "1", "7"));
        var result = ENGINE.calculate(checklist, List.of(answer("a", "scale", BigDecimal.ONE), answer("b", "scale", BigDecimal.ONE)));
        decimal("20.00", result.overall_score()); decimal("2.00", result.sections().getFirst().earned_points());
    }
    @Test void naRenormalizesAndKeepsFlagIndependent() {
        List<CriterionAnswer> answers = seed.criteria().stream().map(c -> c.id().equals("C03") ? answer(c.id(), "na", null)
            : c.kind().equals("scale") ? answer(c.id(), "scale", c.id().equals("C06") ? new BigDecimal("7.0") : new BigDecimal("20"))
            : answer(c.id(), "yes", null)).toList();
        var result = ENGINE.calculate(seed, answers);
        decimal("94.38", result.overall_score()); decimal("80", result.applicable_weight());
        decimal("10.50", result.criteria().get(5).raw_points()); decimal("13.13", result.criteria().get(5).earned_points());
        assertTrue(result.critical_violation()); assertEquals(List.of("C08"), result.critical_criterion_ids());
        var changed = new ArrayList<>(answers); changed.set(7, answer("C08", "no", null));
        assertEquals(result.overall_score(), ENGINE.calculate(seed, changed).overall_score());
    }
    @Test void allNaAndWeightlessFlagsProduceNullTotalAndSectionPercent() {
        Criterion flag = new Criterion("gross", "s", "Gross", "Detect violation", "flag", BigDecimal.ZERO, false, null, List.of());
        var result = ENGINE.calculate(custom(scale("a", "27", true, "0", "2"), flag),
            List.of(answer("a", "na", null), answer("gross", "yes", null)));
        assertNull(result.overall_score()); assertNull(result.max_score()); decimal("0", result.applicable_weight());
        assertTrue(result.critical_violation()); assertTrue(result.sections().stream().allMatch(s -> s.percent() == null));
        assertTrue(result.criteria().stream().allMatch(c -> c.earned_points() == null && c.raw_points() == null && c.effective_weight() == null));
    }
    @Test void halfUpAtTieAndEitherSideWithoutPrematureDecimalRounding() {
        for (String selected : List.of("0.99999999999999999999999999999999999999", "1", "1.00000000000000000000000000000000000001")) {
            var result = ENGINE.calculate(custom(scale("a", "100", false, "0", selected, "20000")),
                List.of(answer("a", "scale", new BigDecimal(selected))));
            decimal(selected.startsWith("0.") ? "0.00" : "0.01", result.overall_score());
        }
    }
    @Test void noCriterionIdsAreHardCodedAndOrderIsChecklistOrder() {
        var checklist = custom(scale("jury-added", "100", false, "0", "2.5", "5"));
        var answer = answer("jury-added", "scale", new BigDecimal("2.500"));
        var result = ENGINE.calculate(checklist, List.of(answer));
        decimal("50", result.overall_score()); assertEquals("jury-added", result.criteria().getFirst().criterion_id());
        assertEquals("cqa-score/1", ScoringEngine.VERSION);
    }
    @Test void invalidScoringInputsFailEvenWithoutJson() {
        var valid = custom(scale("a", "100", false, "0", "1", "3"));
        for (CriterionAnswer invalid : List.of(answer("a", "scale", new BigDecimal("2")), answer("a", "na", null),
                answer("a", "yes", null), answer("unknown", "scale", BigDecimal.ONE),
                new CriterionAnswer("a", "scale", BigDecimal.ONE, "\u00a0", List.of(new Evidence("m0001", "Synthetic"))),
                new CriterionAnswer("a", "scale", BigDecimal.ONE, "Explanation", List.of()))) {
            assertThrows(ContractViolation.class, () -> ENGINE.calculate(valid, List.of(invalid)));
        }
        assertThrows(ContractViolation.class, () -> ENGINE.calculate(valid, List.of()));
        assertThrows(ContractViolation.class, () -> ENGINE.calculate(valid, List.of(answer("a", "scale", BigDecimal.ONE), answer("a", "scale", BigDecimal.ONE))));
        var duplicate = custom(scale("a", "100", false, "0", "1", "1.0"));
        assertThrows(ContractViolation.class, () -> ENGINE.calculate(duplicate, List.of(answer("a", "scale", BigDecimal.ONE))));
    }
}
