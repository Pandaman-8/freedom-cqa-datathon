package cqa.ml;

import cqa.api.*;
import cqa.api.ApiModels.*;
import cqa.dto.*;
import cqa.repository.EvaluationRepository;
import cqa.scoring.ScoringEngine;
import cqa.service.EvaluationService;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.net.URI;
import java.time.Instant;
import java.util.*;

@Service
public class AutoEvaluationService {
    private final EvaluationService evaluations;
    private final EvaluationRepository repository;
    private final RequestLedger ledger;
    private final MlClient client;
    private final SyntheticPolicy policy;
    private final ContractJson json;
    private final ScoringEngine scorer;
    private final TransactionTemplate writes;
    public AutoEvaluationService(EvaluationService evaluations, EvaluationRepository repository, RequestLedger ledger,
            MlClient client, SyntheticPolicy policy, ContractJson json, ScoringEngine scorer, TransactionTemplate writes) {
        this.evaluations=evaluations;this.repository=repository;this.ledger=ledger;this.client=client;
        this.policy=policy;this.json=json;this.scorer=scorer;this.writes=writes;
    }
    public RequestLedger.Status status(String id) {
        if(!id.matches(ContractJson.UUID_PATTERN))throw ApiFailure.invalid();
        var entry=ledger.find(id);if(entry==null)throw ApiFailure.missing();return entry.view();
    }
    private ResponseEntity<?> replay(AutoRequest payload, RequestLedger.Entry entry) {
        if(!payload.equals(entry.payload()))throw new MlFailure(409,"REQUEST_ID_CONFLICT",false,false);
        var status=entry.view();
        return switch(status.status()) {
            case "succeeded" -> ResponseEntity.ok(evaluations.get(status.evaluation_id()));
            case "pending" -> ResponseEntity.accepted().location(URI.create("/api/evaluation-requests/"+payload.request_id())).body(status);
            default -> ResponseEntity.status(entry.httpStatus()).body(new ContractError(status.error()));
        };
    }
    public ResponseEntity<?> evaluate(AutoRequest payload) {
        json.validateShape(payload);
        var existing=ledger.find(payload.request_id());if(existing!=null)return replay(payload,existing);
        var context=evaluations.pin(payload.conversation_id(),payload.checklist_key(),payload.checklist_version());
        client.endpoint(); // Preserve unconfigured501 without side effects, including on non-synthetic data.
        var pinned=new EvaluationRequest("2.0.0",payload.request_id(),context.conversation().projection(),context.checklist());
        ContractValidation.request(pinned);policy.requireApproved(pinned);
        byte[] bytes=client.encode(pinned);
        boolean owner=Boolean.TRUE.equals(writes.execute(tx -> ledger.claim(payload,pinned)));
        if(!owner)return replay(payload,Objects.requireNonNull(ledger.find(payload.request_id())));
        try {
            // No SQLite transaction/connection is held during HTTP. Never read latest again.
            var result=client.evaluate(pinned,bytes);
            var score=scorer.calculate(pinned.checklist(),result.answers());
            var saved=new EvaluationView(UUID.randomUUID().toString(),pinned.conversation().id(),pinned.checklist().key(),
                pinned.checklist().version(),"model",Instant.now().toString(),result.answers(),score,result.answers(),score,
                List.of(),"evaluated","2.0.0",ScoringEngine.VERSION,0);
            writes.executeWithoutResult(tx -> {
                repository.insert(saved);
                ledger.succeed(payload.request_id(),saved.id(),result.diagnostics());
            });
        } catch(MlFailure failure) {
            writes.executeWithoutResult(tx -> ledger.fail(payload.request_id(),failure));
        } catch(RuntimeException failure) {
            // Storage/finalization may fail after inference. Do not infer again or persist a partial result.
            writes.executeWithoutResult(tx -> ledger.fail(payload.request_id(),new MlFailure(502,"EVALUATOR_PROVIDER_ERROR",true,true)));
        }
        return replay(payload,Objects.requireNonNull(ledger.find(payload.request_id())));
    }
}
