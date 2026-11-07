package cqa.dto;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.math.BigDecimal;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;

/** Composition/identity/grounding rules shared by all future Java entry points. */
public final class ContractValidation {
    private static final Validator SHAPE = Validation.buildDefaultValidatorFactory().getValidator();
    private static final Map<Integer, Set<String>> ERROR_CODES = Map.of(
        422, Set.of("INVALID_INPUT", "INPUT_TOO_LARGE", "UNSUPPORTED_CONTRACT"),
        404, Set.of("NOT_FOUND"), 409, Set.of("VERSION_CONFLICT", "REVIEW_CONFLICT", "REQUEST_ID_CONFLICT"),
        501, Set.of("EVALUATOR_UNCONFIGURED"),
        502, Set.of("EVALUATOR_INVALID_OUTPUT", "EVALUATOR_PROVIDER_ERROR"),
        503, Set.of("EVALUATOR_RATE_LIMITED", "EVALUATOR_AUTH", "PRIVACY_POLICY_UNCONFIGURED", "EVALUATOR_BUSY"),
        504, Set.of("EVALUATOR_TIMEOUT"), 413, Set.of("PAYLOAD_TOO_LARGE"));
    private ContractValidation() {}

    private static void shape(Object value) {
        if (value == null || !SHAPE.validate(value).isEmpty())
            throw new ContractViolation(ContractViolation.Layer.SHAPE, "invalid_dto");
    }
    private static void require(boolean condition, String rule) {
        if (!condition) throw new ContractViolation(ContractViolation.Layer.CONTEXT, rule);
    }

    public static void checklist(Checklist checklist) {
        shape(checklist);
        Set<String> sections = new HashSet<>();
        for (Section section : checklist.sections()) require(sections.add(section.id()), "unique_section_ids");
        Set<String> criteria = new HashSet<>();
        boolean positiveWeight = false;
        for (Criterion criterion : checklist.criteria()) {
            require(criteria.add(criterion.id()), "unique_criterion_ids");
            require(sections.contains(criterion.section_id()), "existing_section");
            if (criterion.allow_na()) require(Text.Check.hasText(criterion.na_rule()), "nonblank_na_rule");
            if (criterion.kind().equals("flag")) {
                require(criterion.weight().signum() == 0 && !criterion.allow_na() && criterion.levels().isEmpty(),
                    "weightless_flag_without_na_or_levels");
            } else {
                require(criterion.weight().signum() > 0, "positive_nonflag_weight");
                positiveWeight = true;
            }
            if (criterion.kind().equals("scale")) {
                SortedSet<BigDecimal> levels = new TreeSet<>();
                for (ScaleLevel level : criterion.levels()) require(levels.add(level.value()), "unique_scale_levels");
                require(levels.size() >= 2, "at_least_two_scale_levels");
                require(levels.first().signum() == 0 && levels.last().signum() > 0, "scale_zero_and_positive_max");
            } else require(criterion.levels().isEmpty(), "non_scale_has_no_levels");
        }
        require(positiveWeight, "positive_weight_exists");
    }

    public static void request(EvaluationRequest request) {
        shape(request);
        checklist(request.checklist());
        conversation(request.conversation());
    }

    public static void conversation(SourceConversation conversation) {
        shape(conversation);
        for (int i = 0; i < conversation.messages().size(); i++) {
            String expected = "m" + String.format(Locale.ROOT, "%04d", i + 1);
            require(expected.equals(conversation.messages().get(i).id()), "ordered_positional_message_ids");
        }
    }

    /** Checks scoring inputs even when created directly in Java rather than decoded. */
    public static void answers(Checklist checklist, List<CriterionAnswer> answers) {
        checklist(checklist);
        require(answers != null && answers.size() == checklist.criteria().size(), "complete_answer_set");
        Map<String, Criterion> criteria = checklist.criteria().stream()
            .collect(Collectors.toMap(Criterion::id, Function.identity()));
        Set<String> seen = new HashSet<>();
        for (CriterionAnswer answer : answers) {
            shape(answer);
            require(seen.add(answer.criterion_id()) && criteria.containsKey(answer.criterion_id()), "complete_answer_set");
            Criterion criterion = criteria.get(answer.criterion_id());
            if (answer.answer().equals("na")) {
                require(criterion.allow_na() && !criterion.kind().equals("flag"), "allowed_na");
            } else if (criterion.kind().equals("scale")) {
                require(answer.answer().equals("scale"), "scale_answer_kind");
                require(criterion.levels().stream().anyMatch(level -> level.value().compareTo(answer.value()) == 0),
                    "configured_discrete_scale_value");
            } else require(Set.of("yes", "no").contains(answer.answer()), "binary_or_flag_answer_kind");
        }
    }

    public static void groundedAnswers(EvaluationRequest request, List<CriterionAnswer> answers) {
        request(request);
        answers(request.checklist(), answers);
        Map<String, String> messages = request.conversation().messages().stream()
            .collect(Collectors.toMap(SourceMessage::id, SourceMessage::text));
        for (CriterionAnswer answer : answers) for (Evidence evidence : answer.evidence()) {
            require(messages.containsKey(evidence.message_id()), "existing_message_id");
            require(messages.get(evidence.message_id()).contains(evidence.quote()), "exact_quote_without_normalization");
        }
    }

    public enum Mode { OFFLINE_FIXTURE, PRODUCTION }

    public static void result(EvaluationRequest request, EvaluationResult result, Mode mode) {
        request(request);
        shape(result);
        require(result.contract_version().equals(request.contract_version()), "echo_contract_version");
        require(result.request_id().equals(request.request_id()), "echo_request_id");
        require(result.conversation_id().equals(request.conversation().id()), "echo_conversation_id");
        require(result.checklist_key().equals(request.checklist().key()), "echo_checklist_key");
        require(result.checklist_version().equals(request.checklist().version()), "echo_checklist_version");
        require(mode != null, "validation_mode_required");
        if (mode == Mode.PRODUCTION) require(result.diagnostics().attempt_count().signum() > 0, "production_attempts");
        groundedAnswers(request, result.answers());
    }

    public static void provider(EvaluationRequest request, ProviderOutput output) {
        shape(output);
        groundedAnswers(request, output.answers());
    }

    public static void error(ContractError error, int httpStatus, EvaluationRequest request) {
        shape(error);
        require(ERROR_CODES.getOrDefault(httpStatus, Set.of()).contains(error.detail().code()), "documented_http_status_code_pair");
        if (request != null) {
            request(request);
            require(request.request_id().equals(error.detail().request_id()), "error_request_id_echo");
        }
    }
}
