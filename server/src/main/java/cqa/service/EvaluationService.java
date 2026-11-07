package cqa.service;

import cqa.api.ApiFailure;
import cqa.api.ApiModels.*;
import cqa.dataset.Dataset;
import cqa.dto.*;
import cqa.repository.EvaluationRepository;
import cqa.scoring.ScoringEngine;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.math.BigInteger;
import java.time.Instant;
import java.util.*;

@Service
public class EvaluationService {
    private final ConversationService conversations;
    private final ChecklistService checklists;
    private final EvaluationRepository repository;
    private final ScoringEngine scorer;
    private final TransactionTemplate writes;
    private final ContractJson json;
    public EvaluationService(ConversationService conversations, ChecklistService checklists, EvaluationRepository repository,
            ScoringEngine scorer, TransactionTemplate writes, ContractJson json) {
        this.conversations = conversations; this.checklists = checklists; this.repository = repository;
        this.scorer = scorer; this.writes = writes; this.json = json;
    }
    public record PinnedContext(Dataset.Conversation conversation, Checklist checklist) {}
    public PinnedContext pin(String conversation, String key, BigInteger version) {
        if (version == null || version.signum() <= 0) throw ApiFailure.invalid();
        return new PinnedContext(conversations.get(conversation), checklists.get(key, version));
    }
    public EvaluationView manual(ManualRequest request) {
        json.validateShape(request);
        return saveManual(pin(request.conversation_id(), request.checklist_key(), request.checklist_version()), request.answers());
    }
    public EvaluationView saveManual(PinnedContext pinned, List<CriterionAnswer> answers) {
        String id = UUID.randomUUID().toString();
        Checklist checklist = pinned.checklist();
        // Reuse the exact T04 grounding rules; this envelope is local, never sent to ML.
        ContractValidation.groundedAnswers(new EvaluationRequest("2.0.0", id, pinned.conversation().projection(), checklist), answers);
        var score = scorer.calculate(checklist, answers);
        var result = new EvaluationView(id, pinned.conversation().id(), checklist.key(), checklist.version(), "manual",
            Instant.now().toString(), List.copyOf(answers), score, List.copyOf(answers), score, List.of(), "evaluated", "2.0.0", ScoringEngine.VERSION);
        writes.executeWithoutResult(status -> repository.insert(result));
        return result; // Never look up latest while saving or reading the snapshot.
    }
    public void auto(AutoRequest request) {
        json.validateShape(request);
        pin(request.conversation_id(), request.checklist_key(), request.checklist_version());
        throw new ApiFailure(501,"EVALUATOR_UNCONFIGURED","ML evaluator is not configured.");
    }
    public List<EvaluationView> list(String conversation) { return repository.list(conversation); }
    public EvaluationView get(String id) {
        var found = repository.find(id);
        if (found == null) throw ApiFailure.missing();
        return found;
    }
}
