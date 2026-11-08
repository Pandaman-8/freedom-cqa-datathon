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
            boolean selection_allowed, boolean ready, String data_mode, String reason,
            boolean rubric_confirmation_required, String confirmation_scope) {}
    @GetMapping(value="/api/ai/status", produces="application/json")
    public Status status(@RequestParam(required=false) String conversation_id,
            @RequestParam(required=false) String checklist_key, @RequestParam(required=false) String checklist_version) {
        EvaluationRequest pinned=null;
        if (conversation_id != null || checklist_key != null || checklist_version != null) {
            if (conversation_id == null || checklist_key == null) throw cqa.api.ApiFailure.invalid();
            var context=evaluations.pin(conversation_id,checklist_key,RequestBodies.version(checklist_version,true));
            pinned=new EvaluationRequest("2.0.0","00000000-0000-4000-8000-000000000000",
                    context.conversation().projection(),context.checklist());
        }
        var admission=policy.inspect(pinned);
        var health=client.health();
        String reason=MlClient.admissionMismatch(health,policy.mode(),admission);
        return new Status(health.configured(),health.reachable(),health.ready(),pinned!=null&&admission.allowed(),
                pinned!=null&&reason==null,policy.mode(),reason,admission.confirmationRequired(),admission.grantSha256());
    }
}
