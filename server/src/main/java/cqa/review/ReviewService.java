package cqa.review;

import cqa.api.ApiFailure;
import cqa.api.ApiModels.EvaluationView;
import cqa.dto.*;
import cqa.repository.*;
import cqa.review.ReviewModels.*;
import cqa.scoring.ScoringEngine;
import cqa.service.ChecklistService;
import cqa.service.ConversationService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.time.Instant;
import java.util.*;

@Service
public class ReviewService {
    private final EvaluationRepository evaluations;
    private final ReviewRepository reviews;
    private final ChecklistService checklists;
    private final ConversationService conversations;
    private final ContractJson json;
    private final ScoringEngine scorer;
    private final TransactionTemplate transactions;

    public ReviewService(EvaluationRepository evaluations, ReviewRepository reviews, ChecklistService checklists,
            ConversationService conversations, ContractJson json, ScoringEngine scorer, TransactionTemplate transactions) {
        this.evaluations = evaluations; this.reviews = reviews; this.checklists = checklists;
        this.conversations = conversations; this.json = json; this.scorer = scorer; this.transactions = transactions;
    }
    private EvaluationView original(String id) {
        var evaluation = evaluations.find(id);
        if (evaluation == null) throw ApiFailure.missing();
        return evaluation;
    }
    private Checklist checklist(EvaluationView evaluation) {
        return checklists.get(evaluation.checklist_key(), evaluation.checklist_version());
    }
    private void grounded(EvaluationView evaluation, Checklist checklist, List<CriterionAnswer> answers) {
        ContractValidation.groundedAnswers(new EvaluationRequest("2.0.0", evaluation.id(),
            conversations.get(evaluation.conversation_id()).projection(), checklist), answers);
    }
    private List<CriterionAnswer> replace(List<CriterionAnswer> answers, CriterionAnswer replacement) {
        return answers.stream().map(a -> a.criterion_id().equals(replacement.criterion_id()) ? replacement : a).toList();
    }
    /** Called inside a transaction so history and revision describe one SQLite snapshot. */
    private EvaluationView project(EvaluationView original) {
        var history = reviews.list(original.id());
        var answers = original.original_answers();
        var changes = history.stream().filter(a -> "resolved".equals(a.status()) && "change".equals(a.decision()))
            .sorted(Comparator.comparingLong(AppealView::resolved_revision)).toList();
        for (var appeal : changes) answers = replace(answers, appeal.replacement());
        var score = original.original_score();
        if (!changes.isEmpty()) {
            var pinned = checklist(original);
            grounded(original, pinned, answers);
            score = scorer.calculate(pinned, answers);
        }
        String status = history.isEmpty() ? "evaluated" : history.stream().anyMatch(a -> a.status().equals("open")) ? "appealed" : "reviewed";
        return new EvaluationView(original.id(), original.conversation_id(), original.checklist_key(), original.checklist_version(),
            original.origin(), original.created_at(), original.original_answers(), original.original_score(),
            answers, score, history, status, original.contract_version(), original.scoring_version(), reviews.revision(original.id()));
    }
    public EvaluationView get(String id) { return transactions.execute(status -> project(original(id))); }
    public List<EvaluationView> list(String conversation) {
        return transactions.execute(status -> evaluations.list(conversation).stream().map(this::project).toList());
    }
    public AppealView create(String evaluationId, AppealRequest request) {
        json.validateShape(request);
        return transactions.execute(status -> {
            var evaluation = original(evaluationId);
            if (checklist(evaluation).criteria().stream().noneMatch(c -> c.id().equals(request.criterion_id()))) throw ApiFailure.invalid();
            long revision = reviews.revision(evaluationId);
            if (!reviews.advance(evaluationId, revision)) throw ApiFailure.reviewConflict();
            var appeal = new AppealView(UUID.randomUUID().toString(), evaluationId, request.criterion_id(), request.comment(),
                "open", null, null, null, Instant.now().toString(), null, revision + 1, null);
            if (!reviews.insert(appeal)) throw ApiFailure.reviewConflict(); // Rolls back the revision too.
            return appeal;
        });
    }
    public EvaluationView resolve(String id, long expected, Resolution request) {
        json.validateShape(request);
        return transactions.execute(status -> {
            var appeal = reviews.find(id);
            if (appeal == null) throw ApiFailure.missing();
            if (!appeal.status().equals("open") || reviews.revision(appeal.evaluation_id()) != expected) throw ApiFailure.reviewConflict();
            var current = project(original(appeal.evaluation_id()));
            var answers = current.final_answers();
            if (request.replacement() != null) {
                if (!appeal.criterion_id().equals(request.replacement().criterion_id())) throw ApiFailure.invalid();
                answers = replace(answers, request.replacement());
            }
            var pinned = checklist(current);
            grounded(current, pinned, answers);
            scorer.calculate(pinned, answers); // Validate/recalculate before any writes, including confirm.
            if (!reviews.advance(current.id(), expected)
                    || !reviews.resolve(id, request, Instant.now().toString(), expected + 1)) throw ApiFailure.reviewConflict();
            return project(current);
        });
    }
}
