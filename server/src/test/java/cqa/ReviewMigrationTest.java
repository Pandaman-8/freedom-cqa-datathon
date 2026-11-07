package cqa;

import cqa.dataset.Dataset;
import cqa.dto.*;
import cqa.repository.StorageInitializer;
import cqa.scoring.ScoringEngine;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.sqlite.SQLiteConfig;
import org.sqlite.SQLiteDataSource;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ReviewMigrationTest {
    @TempDir Path directory;

    @Test void populatedT05FileUpgradesAdditivelyAndIdempotentlyWithoutTouching65SyntheticSources() throws Exception {
        Path path = directory.resolve("existing-t05.sqlite");
        SQLiteConfig config = new SQLiteConfig(); config.enforceForeignKeys(true);
        SQLiteDataSource source = new SQLiteDataSource(config); source.setUrl("jdbc:sqlite:" + path);
        var old = new JdbcTemplate(source);
        // Frozen schema from the T05 commit, not a subset derived from today's schema.
        var schema = new ResourceDatabasePopulator(new ClassPathResource("db/t05-schema.sql")); schema.setSeparator(";;");
        try (var connection = source.getConnection()) { schema.populate(connection); }
        assertEquals(0, old.queryForObject("SELECT count(*) FROM sqlite_master WHERE name IN ('appeals','evaluation_reviews')", Integer.class));
        String evaluation = "11111111-1111-4111-8111-111111111111";
        try (var codec = new ContractJson()) {
            var fixture = codec.readRequest(Files.readAllBytes(Path.of("../contracts/fixtures/positive/evaluation_request.json")));
            var answers = codec.readProviderOutput(Files.readAllBytes(Path.of("../contracts/fixtures/positive/provider_output.json")), fixture).answers();
            var checklist = fixture.checklist();
            old.update("INSERT INTO checklists VALUES(?,?,?,?)", checklist.key(), checklist.version().toString(), encode(codec, checklist), "synthetic-t05");
            old.update("INSERT INTO checklist_heads VALUES(?,?)", checklist.key(), checklist.version().toString());
            var turns = fixture.conversation().messages().stream().map(m -> new Dataset.Turn(m.timestamp(), m.speaker(), m.text())).toList();
            for (int i = 0; i < 65; i++) {
                var record = new Dataset.Record("record-" + i, "agent chat", "EN", turns, null);
                old.update("INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?)", "SYNTHETIC-T05:record-" + i,
                    "SYNTHETIC-T05", record.conversation_id(), "EN", "agent chat", turns.size(), encode(codec, record), "synthetic-hash-" + i, "synthetic-t05");
            }
            old.update("INSERT INTO evaluations VALUES(?,?,?,?,?,?,?,?,?)", evaluation, "SYNTHETIC-T05:record-0", checklist.key(),
                checklist.version().toString(), "manual", ScoringEngine.VERSION, encode(codec, new ProviderOutput(answers)),
                encode(codec, new ScoringEngine().calculate(checklist, answers)), "synthetic-t05");
        }
        var beforeSources = old.queryForList("SELECT * FROM conversations ORDER BY id");
        var beforeEvaluation = old.queryForMap("SELECT * FROM evaluations WHERE id=?", evaluation);
        var beforeChecklist = old.queryForMap("SELECT * FROM checklists WHERE key='synthetic-contract'");
        var beforeTriggers = old.queryForList("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name");
        try (var app = (ServletWebServerApplicationContext) new SpringApplicationBuilder(Application.class).run(
                "--server.port=0", "--cqa.db-path=" + path, "--spring.main.banner-mode=off", "--logging.level.root=WARN");
             var client = HttpClient.newHttpClient()) {
            var db = app.getBean(JdbcTemplate.class);
            app.getBean(StorageInitializer.class).afterPropertiesSet(); // A second initialization must be harmless.
            assertEquals(beforeSources, db.queryForList("SELECT * FROM conversations ORDER BY id"));
            assertEquals(beforeEvaluation, db.queryForMap("SELECT * FROM evaluations WHERE id=?", evaluation));
            assertEquals(beforeChecklist, db.queryForMap("SELECT * FROM checklists WHERE key='synthetic-contract'"));
            for (var trigger : beforeTriggers) assertEquals(trigger.get("sql"), db.queryForObject("SELECT sql FROM sqlite_master WHERE name=?", String.class, trigger.get("name")));
            assertTrue(db.queryForList("PRAGMA foreign_key_check").isEmpty());
            String base = "http://127.0.0.1:" + app.getWebServer().getPort();
            var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            var response = client.send(HttpRequest.newBuilder(URI.create(base + "/api/evaluations/" + evaluation)).timeout(Duration.ofSeconds(15)).GET().build(), HttpResponse.BodyHandlers.ofString());
            assertEquals(200, response.statusCode()); var view = mapper.readTree(response.body());
            assertEquals(0, view.get("review_revision").asInt()); assertEquals("evaluated", view.get("review_status").asText());
            assertEquals(view.get("original_score"), view.get("final_score")); assertEquals(100, view.at("/original_score/overall_score").asInt());
            assertEquals(mapper.readTree((String) beforeEvaluation.get("score_json")), view.get("original_score"));
            assertEquals(mapper.readTree((String) beforeEvaluation.get("answers_json")).get("answers"), view.get("original_answers"));
            var appealRequest = HttpRequest.newBuilder(URI.create(base + "/api/evaluations/" + evaluation + "/appeals"))
                .timeout(Duration.ofSeconds(15)).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{\"criterion_id\":\"S_CLARITY\",\"comment\":\"Synthetic migrated evaluation\"}")).build();
            var appeal = client.send(appealRequest, HttpResponse.BodyHandlers.ofString()); assertEquals(201, appeal.statusCode());
            String id = mapper.readTree(appeal.body()).get("id").asText();
            var resolved = client.send(HttpRequest.newBuilder(URI.create(base + "/api/appeals/" + id + "/resolve?expected_revision=1"))
                .timeout(Duration.ofSeconds(15)).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{\"decision\":\"confirm\",\"reason\":\"Synthetic confirmation\"}")).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals(200, resolved.statusCode()); assertEquals("reviewed", mapper.readTree(resolved.body()).get("review_status").asText());
            assertEquals(beforeSources, db.queryForList("SELECT * FROM conversations ORDER BY id"));
            assertEquals(beforeEvaluation, db.queryForMap("SELECT * FROM evaluations WHERE id=?", evaluation));
            assertThrows(org.springframework.dao.DataAccessException.class, () -> db.update("DELETE FROM evaluations WHERE id=?", evaluation));
            assertThrows(org.springframework.dao.DataAccessException.class, () -> db.update("UPDATE evaluations SET score_json='{}' WHERE id=?", evaluation));
        }
    }
    private static String encode(ContractJson codec, Object dto) { return new String(codec.write(dto), StandardCharsets.UTF_8); }
}
