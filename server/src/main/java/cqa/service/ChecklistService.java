package cqa.service;

import cqa.api.ApiFailure;
import cqa.api.ApiModels.ChecklistDraft;
import cqa.dto.*;
import cqa.repository.ChecklistRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.math.BigInteger;
import java.util.List;

@Service
public class ChecklistService {
    private final ChecklistRepository repository;
    private final TransactionTemplate writes;
    public ChecklistService(ChecklistRepository repository, TransactionTemplate writes) { this.repository = repository; this.writes = writes; }
    public List<Checklist> list() { return repository.list(); }
    public Checklist get(String key, BigInteger version) {
        Checklist found = repository.find(key, version);
        if (found == null) throw ApiFailure.missing();
        return found;
    }
    public Checklist create(String key, ChecklistDraft draft) {
        Checklist candidate = draft.versioned(key, BigInteger.ONE);
        ContractValidation.checklist(candidate);
        return writes.execute(status -> {
            if (repository.find(key, null) != null) throw ApiFailure.conflict();
            repository.insert(candidate); repository.createHead(candidate); return candidate;
        });
    }
    public Checklist update(String key, BigInteger expected, ChecklistDraft draft) {
        if (expected == null || expected.signum() <= 0) throw ApiFailure.invalid();
        Checklist candidate = draft.versioned(key, expected.add(BigInteger.ONE));
        ContractValidation.checklist(candidate);
        return writes.execute(status -> {
            Checklist current = get(key, null);
            if (!expected.equals(current.version())) throw ApiFailure.conflict();
            repository.insert(candidate);
            if (!repository.advanceHead(key, expected, candidate.version())) throw ApiFailure.conflict();
            return candidate;
        });
    }
}
