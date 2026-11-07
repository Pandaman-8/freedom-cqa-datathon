package cqa.repository;

import cqa.dto.CriterionAnswer;
import cqa.review.ReviewModels.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public class ReviewRepository {
    private final JdbcTemplate db;
    private final StoredJson json;
    public ReviewRepository(JdbcTemplate db, StoredJson json) { this.db = db; this.json = json; }

    public long revision(String evaluation) {
        var rows = db.queryForList("SELECT revision FROM evaluation_reviews WHERE evaluation_id=?", Long.class, evaluation);
        return rows.isEmpty() ? 0 : rows.getFirst();
    }
    /** Caller owns the IMMEDIATE transaction; the CAS and subsequent appeal write commit together. */
    public boolean advance(String evaluation, long expected) {
        if (expected < 0 || expected == Long.MAX_VALUE) return false;
        db.update("INSERT INTO evaluation_reviews(evaluation_id,revision) VALUES(?,0) ON CONFLICT(evaluation_id) DO NOTHING", evaluation);
        return db.update("UPDATE evaluation_reviews SET revision=revision+1 WHERE evaluation_id=? AND revision=?",
            evaluation, expected) == 1;
    }
    public boolean insert(AppealView appeal) {
        return db.update("""
            INSERT INTO appeals(id,evaluation_id,criterion_id,comment,status,created_at,created_revision)
            VALUES(?,?,?,?,'open',?,?)
            ON CONFLICT(evaluation_id,criterion_id) WHERE status='open' DO NOTHING
            """, appeal.id(), appeal.evaluation_id(), appeal.criterion_id(), appeal.comment(),
            appeal.created_at(), appeal.created_revision()) == 1;
    }
    public boolean resolve(String id, Resolution decision, String time, long revision) {
        return db.update("""
            UPDATE appeals SET status='resolved',decision=?,reason=?,replacement_json=?,resolved_at=?,resolved_revision=?
            WHERE id=? AND status='open'
            """, decision.decision(), decision.reason(), decision.replacement() == null ? null : json.write(decision.replacement()),
            time, revision, id) == 1;
    }
    private RowMapper<AppealView> mapper() {
        return (r, i) -> {
            String replacement = r.getString("replacement_json");
            long resolved = r.getLong("resolved_revision");
            Long revision = r.wasNull() ? null : resolved;
            return new AppealView(r.getString("id"), r.getString("evaluation_id"), r.getString("criterion_id"),
                r.getString("comment"), r.getString("status"), r.getString("decision"), r.getString("reason"),
                replacement == null ? null : json.read(replacement, CriterionAnswer.class),
                r.getString("created_at"), r.getString("resolved_at"), r.getLong("created_revision"), revision);
        };
    }
    public AppealView find(String id) {
        var rows = db.query("SELECT * FROM appeals WHERE id=?", mapper(), id);
        return rows.isEmpty() ? null : rows.getFirst();
    }
    public List<AppealView> list(String evaluation) {
        return db.query("SELECT * FROM appeals WHERE evaluation_id=? ORDER BY created_revision", mapper(), evaluation);
    }
}
