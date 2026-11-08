package cqa.ml;

import cqa.dto.*;
import cqa.api.RequestBodies;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

/** Fail closed against exact immutable fixture values, never a group-name heuristic. */
@Component
public class SyntheticPolicy {
    private final List<EvaluationRequest> approved = new ArrayList<>();
    private final List<SourceConversation> dataset = new ArrayList<>();
    private final String mode;
    private final ContractJson json;
    private final String endpoint;
    private Path grantPath;
    private String grantHash;
    private Grant grant;

    /** Private operator attestation, not the ML wire contract or a browser-controlled switch. */
    public record Grant(String approval_reference, List<String> approved_by, String processing_mode,
            String destination_description, String expires_at, String ml_url, String dataset_path,
            String dataset_sha256, List<String> conversation_ids, List<Checklist> checklist_snapshots) {}

    @Autowired
    public SyntheticPolicy(ContractJson json, @Value("${cqa.ml-data-mode:synthetic_only}") String mode,
            @Value("${cqa.ml-approval-file:}") String approvalFile, @Value("${cqa.ml-url:}") String endpoint) throws IOException {
        this.mode = mode; this.json=json; this.endpoint=endpoint;
        if (mode.equals("synthetic_only")) {
        var resources = new PathMatchingResourcePatternResolver().getResources("classpath*:ml/synthetic/*/request.json");
        for (var resource : resources) try (var input = resource.getInputStream()) {
            approved.add(json.readRequest(input.readNBytes(ContractJson.REQUEST_LIMIT + 1)));
        }
        if (approved.size() != 6) throw new IllegalStateException("Synthetic ML policy resources are incomplete");
        }
        if (mode.equals("approved_dataset")) {
            try { grantPath=Path.of(approvalFile); reloadGrant(); }
            catch (RuntimeException invalid) { grant=null; }
        }
    }
    private void reloadGrant() {
        grant=null; dataset.clear();
        try {
            if (!grantPath.isAbsolute()) throw new IllegalArgumentException();
            byte[] bytes = bounded(grantPath, ContractJson.REQUEST_LIMIT);
            var candidate = json.read(bytes, Grant.class);
            if (candidate.approval_reference() == null || candidate.approval_reference().isBlank()
                    || candidate.destination_description() == null || candidate.destination_description().isBlank()
                    || candidate.approved_by() == null || !new HashSet<>(candidate.approved_by()).equals(Set.of("Farhat", "Nurtas"))
                    || !Set.of("local_only", "external_approved").contains(candidate.processing_mode())
                    || !endpoint.equals(candidate.ml_url()) || endpoint.isBlank()
                    || candidate.conversation_ids() == null || candidate.conversation_ids().isEmpty()
                    || candidate.conversation_ids().stream().anyMatch(k -> k == null || k.isBlank())
                    || candidate.checklist_snapshots() == null || candidate.checklist_snapshots().isEmpty()
                    || candidate.checklist_snapshots().contains(null)
                    || !Instant.now().isBefore(Instant.parse(candidate.expires_at()))) throw new IllegalArgumentException();
            Path source = Path.of(candidate.dataset_path());
            if (!source.isAbsolute()) throw new IllegalArgumentException();
            byte[] input = bounded(source, RequestBodies.DATASET_LIMIT);
            if (!hash(input).equals(candidate.dataset_sha256())) throw new IllegalArgumentException();
            var envelope = new RequestBodies(json).dataset(input);
            var data = envelope.data();
            if (!envelope.isSuccess() || !envelope.error().isEmpty()
                    || !data.total_records().equals(java.math.BigInteger.valueOf(data.records().size()))
                    || data.records().isEmpty()) throw new IllegalArgumentException();
            Set<String> ids = new HashSet<>();
            for (var r : data.records()) {
                if (!ids.add(r.conversation_id())) throw new IllegalArgumentException();
                dataset.add(new SourceConversation(data.dataset_group_id()+":"+r.conversation_id(), data.dataset_group_id(),
                        r.conversation_id(), r.channel(), r.language(), r.messages()));
            }
            if (!dataset.stream().map(SourceConversation::id).collect(java.util.stream.Collectors.toSet())
                    .containsAll(candidate.conversation_ids())) throw new IllegalArgumentException();
            grantHash = hash(bytes); grant = candidate;
        } catch (Exception invalid) {
            // Never log private paths, transcript, approval contents or credentials. Fail closed.
            dataset.clear(); grant = null;
        }
    }
    public String mode() { return Set.of("synthetic_only", "approved_dataset").contains(mode) ? mode : "invalid"; }
    public synchronized void requireApproved(EvaluationRequest request) {
        if (mode.equals("synthetic_only") && approved.stream().anyMatch(a ->
                a.conversation().equals(request.conversation()) && a.checklist().equals(request.checklist()))) return;
        if (mode.equals("approved_dataset")) try {
            if (grantPath == null || !grantPath.isAbsolute()) throw new IllegalArgumentException();
            if (grant == null || !hash(bounded(grantPath, ContractJson.REQUEST_LIMIT)).equals(grantHash)) reloadGrant();
            if (grant == null) throw new IllegalArgumentException();
            // Revocation/removal/edit of the private grant takes effect without restarting Java.
            if (Instant.now().isBefore(Instant.parse(grant.expires_at()))
                    && grantHash.equals(hash(bounded(grantPath, ContractJson.REQUEST_LIMIT)))
                    && grant.conversation_ids().contains(request.conversation().id())
                    && grant.checklist_snapshots().contains(request.checklist())
                    && dataset.contains(request.conversation())) return;
        } catch (Exception revoked) { /* Fail closed, with no private details. */ }
        throw new MlFailure(503,"PRIVACY_POLICY_UNCONFIGURED",false,false);
    }
    private static byte[] bounded(Path path, int limit) throws IOException {
        try (var stream = Files.newInputStream(path)) {
            byte[] data = stream.readNBytes(limit + 1);
            if (data.length > limit) throw new IOException("approval_limit");
            return data;
        }
    }
    private static String hash(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }
}
