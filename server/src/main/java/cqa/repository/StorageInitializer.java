package cqa.repository;

import cqa.dto.*;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class StorageInitializer implements InitializingBean {
    private final JdbcTemplate db;
    private final TransactionTemplate writes;
    private final ChecklistRepository checklists;
    private final ContractJson json;
    public StorageInitializer(JdbcTemplate db, TransactionTemplate writes, ChecklistRepository checklists, ContractJson json) {
        this.db = db; this.writes = writes; this.checklists = checklists; this.json = json;
    }
    @Override public void afterPropertiesSet() throws Exception {
        Checklist seed;
        try (var input = new ClassPathResource("db/seed/chat_quality.json").getInputStream()) {
            seed = json.read(input.readAllBytes(), Checklist.class);
        }
        ContractValidation.checklist(seed);
        writes.executeWithoutResult(status -> {
            ResourceDatabasePopulator schema = new ResourceDatabasePopulator(new ClassPathResource("db/schema.sql"));
            schema.setSeparator(";;");
            db.execute((ConnectionCallback<Void>) connection -> { schema.populate(connection); return null; });
            checklists.seed(seed);
        });
    }
}
