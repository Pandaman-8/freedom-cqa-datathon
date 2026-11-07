package cqa.ml;

import cqa.dto.*;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.util.*;

/** Fail closed against exact immutable fixture values, never a group-name heuristic. */
@Component
public class SyntheticPolicy {
    private final List<EvaluationRequest> approved = new ArrayList<>();
    public SyntheticPolicy(ContractJson json) throws IOException {
        var resources = new PathMatchingResourcePatternResolver().getResources("classpath*:ml/synthetic/*/request.json");
        for (var resource : resources) try (var input = resource.getInputStream()) {
            approved.add(json.readRequest(input.readNBytes(ContractJson.REQUEST_LIMIT + 1)));
        }
        if (approved.size() != 6) throw new IllegalStateException("Synthetic ML policy resources are incomplete");
    }
    public void requireApproved(EvaluationRequest request) {
        // Checklist text is also outbound data. The first live phase permits exact fixture pairs only.
        if (approved.stream().noneMatch(a -> a.conversation().equals(request.conversation()) && a.checklist().equals(request.checklist())))
            throw new MlFailure(503,"PRIVACY_POLICY_UNCONFIGURED",false,false);
    }
}
