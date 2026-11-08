package cqa.ml;

import cqa.api.RequestBodies;
import cqa.dto.EvaluationRequest;
import cqa.service.EvaluationService;
import org.springframework.web.bind.annotation.*;

/** Additive Java/UI status route. Does not alter the 2.0.0 inference contract. */
@RestController
public class AiStatusController {
    private final MlClient client;
    private final SyntheticPolicy policy;
    private final EvaluationService evaluations;
    public AiStatusController(MlClient client, SyntheticPolicy policy, EvaluationService evaluations) {
        this.client=client; this.policy=policy; this.evaluations=evaluations;
    }
    public record Status(boolean ml_configured, boolean ml_reachable, boolean ml_ready,
            boolean selection_allowed, boolean ready, String data_mode, String reason) {}
    @GetMapping(value="/api/ai/status", produces="application/json")
    public Status status(@RequestParam(required=false) String conversation_id,
            @RequestParam(required=false) String checklist_key, @RequestParam(required=false) String checklist_version) {
        boolean allowed=false;
        if (conversation_id != null || checklist_key != null || checklist_version != null) {
            if (conversation_id == null || checklist_key == null) throw cqa.api.ApiFailure.invalid();
            var context=evaluations.pin(conversation_id,checklist_key,RequestBodies.version(checklist_version,true));
            try {
                policy.requireApproved(new EvaluationRequest("2.0.0","00000000-0000-4000-8000-000000000000",
                        context.conversation().projection(),context.checklist()));
                allowed=true;
            } catch (MlFailure denied) { /* Readiness is explicit; no inference or ledger claim. */ }
        }
        var health=client.health();
        String reason=conversation_id != null && !allowed ? "PRIVACY_POLICY_UNCONFIGURED" : health.reason();
        return new Status(health.configured(),health.reachable(),health.ready(),allowed,
                allowed && health.ready(),policy.mode(),reason);
    }
}
