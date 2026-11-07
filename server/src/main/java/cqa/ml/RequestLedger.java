package cqa.ml;

import cqa.api.ApiModels.AutoRequest;
import cqa.dto.*;
import cqa.repository.StoredJson;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.DependsOn;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.support.TransactionTemplate;
import java.time.Instant;

@Repository
@DependsOn("storageInitializer")
public class RequestLedger implements InitializingBean {
    public record Status(String request_id, String status, String evaluation_id, ErrorDetail error) {}
    public record Entry(AutoRequest payload, Status view, Integer httpStatus) {}
    private final JdbcTemplate db;
    private final StoredJson json;
    private final TransactionTemplate writes;
    public RequestLedger(JdbcTemplate db, StoredJson json, TransactionTemplate writes) {
        this.db=db;this.json=json;this.writes=writes;
    }
    @Override public void afterPropertiesSet() {
        // One Java process owns this DB. Never replay an interrupted call after restart.
        writes.executeWithoutResult(tx -> {
            for(String id:db.queryForList("SELECT request_id FROM evaluation_requests WHERE status='pending'",String.class))
                fail(id,MlFailure.timeout());
        });
    }
    public Entry find(String id) {
        var rows=db.query("SELECT * FROM evaluation_requests WHERE request_id=?",(r,i) ->
            new Entry(json.read(r.getString("payload_json"),AutoRequest.class),
                new Status(r.getString("request_id"),r.getString("status"),r.getString("evaluation_id"),
                    r.getString("error_json")==null?null:json.read(r.getString("error_json"),ErrorDetail.class)),
                (Integer)r.getObject("http_status")),id);
        return rows.isEmpty()?null:rows.getFirst();
    }
    /** Caller holds a short write transaction. Only its INSERT winner may call Python. */
    public boolean claim(AutoRequest payload, EvaluationRequest pinned) {
        return db.update("INSERT INTO evaluation_requests(request_id,payload_json,pinned_request_json,status,created_at) VALUES(?,?,?,'pending',?) ON CONFLICT(request_id) DO NOTHING",
            payload.request_id(),json.write(payload),json.write(pinned),Instant.now().toString())==1;
    }
    public void succeed(String id, String evaluation, Diagnostics diagnostics) {
        if(db.update("UPDATE evaluation_requests SET status='succeeded',evaluation_id=?,diagnostics_json=?,http_status=200,completed_at=? WHERE request_id=? AND status='pending'",
                evaluation,json.write(diagnostics),Instant.now().toString(),id)!=1)
            throw new IllegalStateException("Request is no longer pending");
    }
    public void fail(String id, MlFailure failure) {
        db.update("UPDATE evaluation_requests SET status=?,error_json=?,http_status=?,completed_at=? WHERE request_id=? AND status='pending'",
            failure.unknown?"unknown":"failed",json.write(failure.detail(id)),failure.status,Instant.now().toString(),id);
    }
}
