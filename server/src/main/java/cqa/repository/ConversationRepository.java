package cqa.repository;

import cqa.dataset.Dataset;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.time.Instant;
import java.util.List;

@Repository
public class ConversationRepository {
    private final JdbcTemplate db;
    private final StoredJson json;
    public ConversationRepository(JdbcTemplate db, StoredJson json) { this.db = db; this.json = json; }
    public String hash(String id) {
        var rows = db.queryForList("SELECT content_hash FROM conversations WHERE id=?", String.class, id);
        return rows.isEmpty() ? null : rows.getFirst();
    }
    public void insert(String group, Dataset.Record record, String hash) {
        db.update("INSERT INTO conversations(id,dataset_group_id,conversation_id,language,channel,message_count,source_json,content_hash,imported_at) VALUES(?,?,?,?,?,?,?,?,?)",
            group + ":" + record.conversation_id(), group, record.conversation_id(), record.language(), record.channel(),
            record.transcript().size(), json.write(record), hash, Instant.now().toString());
    }
    public List<Dataset.Summary> list() {
        return db.query("SELECT id,conversation_id,dataset_group_id,language,channel,message_count,imported_at FROM conversations ORDER BY dataset_group_id,conversation_id",
            (r,i) -> new Dataset.Summary(r.getString("id"), r.getString("conversation_id"), r.getString("dataset_group_id"),
                r.getString("language"), r.getString("channel"), r.getInt("message_count"), r.getString("imported_at")));
    }
    public Dataset.Conversation find(String id) {
        var rows = db.query("SELECT * FROM conversations WHERE id=?", (r,i) -> {
            Dataset.Record source = json.read(r.getString("source_json"), Dataset.Record.class);
            return new Dataset.Conversation(r.getString("id"), source.conversation_id(), r.getString("dataset_group_id"), source.language(),
                source.channel(), source.transcript().size(), r.getString("imported_at"), source.transcript(), source.messages(), source.audio_url());
        }, id);
        return rows.isEmpty() ? null : rows.getFirst();
    }
}
