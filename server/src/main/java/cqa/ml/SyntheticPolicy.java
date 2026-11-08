package cqa.ml;

import cqa.dto.*;
import cqa.api.RequestBodies;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.math.BigInteger;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

/** Independent, fail-closed admission. Group labels never authorize data transfer. */
@Component
public class SyntheticPolicy {
    public static final String PROVIDER = "groq", MODEL = "openai/gpt-oss-20b";
    private final List<EvaluationRequest> synthetic = new ArrayList<>();
    private final String mode, endpoint, approvalFile;
    private final ContractJson json;
    private final boolean externalEnabled;

    public record ChecklistScope(String key, BigInteger min_version, BigInteger max_version,
            BigInteger max_criteria, Boolean require_confirmation) {}
    /** Private configuration v2; deliberately rejects legacy checklist_snapshots grants. */
    public record Grant(BigInteger approval_version, String session_id, String approval_reference,
            List<String> approved_by, String processing_mode, String destination_description,
            String expires_at, String ml_url, String dataset_path, String dataset_sha256,
            List<String> conversation_ids, String provider, String model, ChecklistScope checklist_scope) {}
    public record Admission(boolean allowed, String reason, String grantSha256, boolean confirmationRequired) {
        static Admission denied(String reason) { return new Admission(false, reason, null, false); }
    }

    public SyntheticPolicy(ContractJson json, @Value("${cqa.ml-data-mode:synthetic_only}") String mode,
            @Value("${cqa.ml-approval-file:}") String approvalFile, @Value("${cqa.ml-url:}") String endpoint,
            @Value("${cqa.ml-external-inference-enabled:false}") boolean externalEnabled) throws IOException {
        this.mode=mode; this.json=json; this.endpoint=endpoint; this.approvalFile=approvalFile;
        this.externalEnabled=externalEnabled;
        if (mode.equals("synthetic_only")) {
            var resources=new PathMatchingResourcePatternResolver().getResources("classpath*:ml/synthetic/*/request.json");
            for (var resource:resources) try (var input=resource.getInputStream()) {
                synthetic.add(json.readRequest(input.readNBytes(ContractJson.REQUEST_LIMIT+1)));
            }
            if (synthetic.size()!=6) throw new IllegalStateException("Synthetic ML policy resources are incomplete");
        }
    }
    public String mode() { return Set.of("synthetic_only","approved_dataset").contains(mode) ? mode : "invalid"; }
    public void requireApproved(EvaluationRequest request) {
        if (!inspect(request).allowed()) throw new MlFailure(503,"PRIVACY_POLICY_UNCONFIGURED",false,false);
    }
    /** null checks server configuration only, never selected-request readiness. No private values in reasons. */
    public Admission inspect(EvaluationRequest request) {
        if (mode.equals("synthetic_only")) {
            boolean allowed=request==null || synthetic.stream().anyMatch(a ->
                    a.conversation().equals(request.conversation()) && a.checklist().equals(request.checklist()));
            return allowed ? new Admission(true,null,null,false) : Admission.denied("JAVA_SELECTION_DENIED");
        }
        if (!mode.equals("approved_dataset")) return Admission.denied("JAVA_POLICY_MODE_INVALID");
        if (!externalEnabled) return Admission.denied("EXTERNAL_INFERENCE_DISABLED");
        try {
            Path grantPath=Path.of(approvalFile);
            if (!grantPath.isAbsolute()) return Admission.denied("APPROVAL_INVALID");
            byte[] bytes=bounded(grantPath,ContractJson.RESPONSE_LIMIT);
            Grant grant=json.read(bytes,Grant.class);
            ChecklistScope scope=grant.checklist_scope();
            if (!BigInteger.TWO.equals(grant.approval_version()) || !text(grant.session_id())
                    || !text(grant.approval_reference()) || !text(grant.destination_description())
                    || grant.approved_by()==null || grant.approved_by().size()!=2
                    || !new HashSet<>(grant.approved_by()).equals(Set.of("Farhat","Nurtas"))
                    || !"external_approved".equals(grant.processing_mode())
                    || !PROVIDER.equals(grant.provider()) || !MODEL.equals(grant.model())
                    || endpoint.isBlank() || !endpoint.equals(grant.ml_url())
                    || grant.conversation_ids()==null || grant.conversation_ids().isEmpty()
                    || grant.conversation_ids().stream().anyMatch(id -> !text(id))
                    || new HashSet<>(grant.conversation_ids()).size()!=grant.conversation_ids().size()
                    || scope==null || !text(scope.key()) || scope.min_version()==null || scope.min_version().signum()<=0
                    || scope.max_version()==null || scope.max_version().compareTo(scope.min_version())<0
                    || scope.max_criteria()==null || scope.max_criteria().signum()<=0
                    || scope.max_criteria().compareTo(BigInteger.valueOf(100))>0
                    || !Boolean.TRUE.equals(scope.require_confirmation())) return Admission.denied("APPROVAL_INVALID");
            if (!Instant.now().isBefore(Instant.parse(grant.expires_at()))) return Admission.denied("APPROVAL_EXPIRED");
            Path source=Path.of(grant.dataset_path());
            if (!source.isAbsolute()) return Admission.denied("APPROVAL_INVALID");
            // Recheck exact source bytes on every admission, including after a running process sees a file edit.
            byte[] input=bounded(source,RequestBodies.DATASET_LIMIT);
            if (!hash(input).equals(grant.dataset_sha256())) return Admission.denied("DATASET_HASH_MISMATCH");
            var envelope=new RequestBodies(json).dataset(input);var data=envelope.data();
            if (!envelope.isSuccess() || !envelope.error().isEmpty() || data.records().isEmpty()
                    || !data.total_records().equals(BigInteger.valueOf(data.records().size()))) return Admission.denied("APPROVAL_INVALID");
            Map<String,SourceConversation> sources=new HashMap<>();
            for (var r:data.records()) {
                var c=new SourceConversation(data.dataset_group_id()+":"+r.conversation_id(),data.dataset_group_id(),
                        r.conversation_id(),r.channel(),r.language(),r.messages());
                if (sources.put(c.id(),c)!=null) return Admission.denied("APPROVAL_INVALID");
            }
            for (String id:grant.conversation_ids()) {
                var c=sources.get(id);
                if (c==null || !"agent chat".equals(c.channel())) return Admission.denied("APPROVAL_INVALID");
            }
            if (request!=null) {
                ContractValidation.request(request);
                var rubric=request.checklist();var conversation=request.conversation();
                if (!grant.conversation_ids().contains(conversation.id()) || !conversation.equals(sources.get(conversation.id()))
                        || !"agent chat".equals(conversation.channel())) return Admission.denied("JAVA_SELECTION_DENIED");
                if (!scope.key().equals(rubric.key()) || rubric.version().compareTo(scope.min_version())<0
                        || rubric.version().compareTo(scope.max_version())>0
                        || BigInteger.valueOf(rubric.criteria().size()).compareTo(scope.max_criteria())>0)
                    return Admission.denied("CHECKLIST_OUTSIDE_SCOPE");
            }
            String digest=hash(bytes);
            if (!digest.equals(hash(bounded(grantPath,ContractJson.RESPONSE_LIMIT)))) return Admission.denied("APPROVAL_CHANGED");
            return new Admission(true,null,digest,true);
        } catch (Exception invalid) {
            // Private filenames, transcripts, approvals and exceptions never enter logs or error envelopes.
            return Admission.denied("APPROVAL_INVALID");
        }
    }
    private static boolean text(String value) { return value!=null && !value.isBlank(); }
    private static byte[] bounded(Path path,int limit) throws IOException {
        try (var stream=Files.newInputStream(path)) {
            byte[] data=stream.readNBytes(limit+1);
            if(data.length>limit)throw new IOException("admission_limit");
            return data;
        }
    }
    private static String hash(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }
}
