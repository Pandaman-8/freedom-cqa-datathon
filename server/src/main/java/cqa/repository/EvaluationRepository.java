package cqa.repository;

import cqa.api.ApiModels.EvaluationView;
import cqa.api.ApiFailure;
import cqa.dto.*;
import cqa.scoring.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import java.math.BigInteger;
import java.util.List;

@Repository
public class EvaluationRepository {
    private final JdbcTemplate db;
    private final StoredJson json;
    public EvaluationRepository(JdbcTemplate db, StoredJson json) { this.db = db; this.json = json; }
    public void insert(EvaluationView evaluation) {
        db.update("INSERT INTO evaluations(id,conversation_id,checklist_key,checklist_version,origin,scoring_version,answers_json,score_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            evaluation.id(), evaluation.conversation_id(), evaluation.checklist_key(), evaluation.checklist_version().toString(),
            evaluation.origin(), evaluation.scoring_version(), json.write(new ProviderOutput(evaluation.original_answers())),
            json.write(evaluation.original_score()), evaluation.created_at());
    }
    private RowMapper<EvaluationView> mapper() {
        return (r,i) -> {
            // Reject an unknown algorithm before decoding its potentially different score shape.
            if (!ScoringEngine.VERSION.equals(r.getString("scoring_version"))) throw ApiFailure.unsupportedScorer();
            var answers = json.read(r.getString("answers_json"), ProviderOutput.class).answers();
            var score = json.read(r.getString("score_json"), ScoreResult.class);
            return new EvaluationView(r.getString("id"), r.getString("conversation_id"), r.getString("checklist_key"),
                new BigInteger(r.getString("checklist_version")), r.getString("origin"), r.getString("created_at"),
                answers, score, answers, score, List.of(), "evaluated", "2.0.0", r.getString("scoring_version"), 0);
        };
    }
    public EvaluationView find(String id) {
        var rows = db.query("SELECT * FROM evaluations WHERE id=?", mapper(), id);
        return rows.isEmpty() ? null : rows.getFirst();
    }
    public List<EvaluationView> list(String conversation) {
        return conversation == null ? db.query("SELECT * FROM evaluations ORDER BY created_at DESC,id", mapper())
            : db.query("SELECT * FROM evaluations WHERE conversation_id=? ORDER BY created_at DESC,id", mapper(), conversation);
    }
}
