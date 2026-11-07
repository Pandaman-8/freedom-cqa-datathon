package cqa.repository;

import cqa.dto.Checklist;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.math.BigInteger;
import java.time.Instant;
import java.util.List;

@Repository
public class ChecklistRepository {
    private final JdbcTemplate db;
    private final StoredJson json;
    public ChecklistRepository(JdbcTemplate db, StoredJson json) { this.db = db; this.json = json; }
    public Checklist find(String key, BigInteger version) {
        List<String> rows = version == null
            ? db.queryForList("SELECT c.payload_json FROM checklists c JOIN checklist_heads h ON c.key=h.key AND c.version=h.version WHERE c.key=?", String.class, key)
            : db.queryForList("SELECT payload_json FROM checklists WHERE key=? AND version=?", String.class, key, version.toString());
        return rows.isEmpty() ? null : json.read(rows.getFirst(), Checklist.class);
    }
    public List<Checklist> list() {
        return db.queryForList("SELECT c.payload_json FROM checklists c JOIN checklist_heads h ON c.key=h.key AND c.version=h.version ORDER BY c.key", String.class)
            .stream().map(s -> json.read(s, Checklist.class)).toList();
    }
    public void insert(Checklist checklist) {
        db.update("INSERT INTO checklists(key,version,payload_json,created_at) VALUES(?,?,?,?)",
            checklist.key(), checklist.version().toString(), json.write(checklist), Instant.now().toString());
    }
    public void createHead(Checklist checklist) {
        db.update("INSERT INTO checklist_heads(key,version) VALUES(?,?)", checklist.key(), checklist.version().toString());
    }
    public boolean advanceHead(String key, BigInteger expected, BigInteger next) {
        return db.update("UPDATE checklist_heads SET version=? WHERE key=? AND version=?", next.toString(), key, expected.toString()) == 1;
    }
    public void seed(Checklist seed) {
        db.update("INSERT INTO checklists(key,version,payload_json,created_at) VALUES(?,?,?,?) ON CONFLICT(key,version) DO NOTHING",
            seed.key(), seed.version().toString(), json.write(seed), Instant.now().toString());
        db.update("INSERT INTO checklist_heads(key,version) VALUES(?,?) ON CONFLICT(key) DO NOTHING", seed.key(), seed.version().toString());
    }
}
