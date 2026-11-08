package cqa.service;

import cqa.api.ApiFailure;
import cqa.dataset.Dataset;
import cqa.dataset.DatasetSourceStore;
import cqa.dto.ContractJson;
import cqa.repository.ConversationRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.math.BigInteger;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;

@Service
public class ConversationService {
    private final ConversationRepository repository;
    private final TransactionTemplate writes;
    private final ContractJson json;
    private final DatasetSourceStore sources;
    public ConversationService(ConversationRepository repository, TransactionTemplate writes, ContractJson json, DatasetSourceStore sources) {
        this.repository = repository; this.writes = writes; this.json = json; this.sources = sources;
    }
    public List<Dataset.Summary> list() { return repository.list(); }
    public Dataset.Conversation get(String id) {
        var found = repository.find(id);
        if (found == null) throw ApiFailure.missing();
        return found;
    }
    public Dataset.ImportResult importDataset(Dataset.Envelope envelope, byte[] source) {
        json.validateShape(envelope);
        var data = envelope.data();
        if (!envelope.isSuccess() || !envelope.error().isEmpty()
                || !data.total_records().equals(BigInteger.valueOf(data.records().size()))) throw ApiFailure.invalid();
        Set<String> ids = new HashSet<>();
        List<String> hashes = new ArrayList<>();
        Map<String,Integer> languages = new LinkedHashMap<>(Map.of("RU",0,"KZ",0,"EN",0));
        Map<String,Integer> channels = new LinkedHashMap<>(Map.of("agent chat",0,"voice call",0));
        for (var record : data.records()) {
            if (!ids.add(record.conversation_id())) throw ApiFailure.invalid();
            hashes.add(hash(json.write(record)));
            languages.merge(record.language(),1,Integer::sum); channels.merge(record.channel(),1,Integer::sum);
        }
        writes.executeWithoutResult(status -> {
            for (int i=0; i<data.records().size(); i++) {
                var record = data.records().get(i);
                String previous = repository.hash(data.dataset_group_id() + ":" + record.conversation_id());
                if (previous != null && !previous.equals(hashes.get(i))) throw ApiFailure.conflict();
            }
            // Archive before committing any rows. A failed DB commit may leave a valid private
            // source snapshot; a successful import can never lack its exact source bytes.
            sources.save(source);
            for (int i=0; i<data.records().size(); i++) {
                var record = data.records().get(i);
                String previous = repository.hash(data.dataset_group_id() + ":" + record.conversation_id());
                if (previous == null) repository.insert(data.dataset_group_id(), record, hashes.get(i));
            }
        });
        // Matches legacy: count records in this accepted import, including idempotent repeats.
        return new Dataset.ImportResult(data.dataset_group_id(), data.records().size(), languages, channels);
    }
    private static String hash(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException e) { throw new IllegalStateException("SHA-256 unavailable"); }
    }
}
