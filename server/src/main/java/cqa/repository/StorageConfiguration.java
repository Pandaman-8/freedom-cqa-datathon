package cqa.repository;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import cqa.dto.ContractJson;
import cqa.scoring.ScoringEngine;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.sqlite.SQLiteConfig;
import org.sqlite.SQLiteDataSource;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

@Configuration
public class StorageConfiguration {
    @Bean(destroyMethod = "close")
    public HikariDataSource dataSource(@Value("${cqa.db-path}") String configuredPath) {
        Path path = Path.of(configuredPath).normalize();
        if (!path.isAbsolute()) throw new IllegalStateException("CQA_DB_PATH must be absolute");
        try { Files.createDirectories(path.getParent()); }
        catch (IOException e) { throw new IllegalStateException("Cannot initialize storage directory"); }
        SQLiteConfig sqlite = new SQLiteConfig();
        sqlite.enforceForeignKeys(true);
        sqlite.setBusyTimeout(5000);
        sqlite.setJournalMode(SQLiteConfig.JournalMode.WAL);
        // Reserve the SQLite writer before a transaction reads latest version/hash.
        sqlite.setTransactionMode(SQLiteConfig.TransactionMode.IMMEDIATE);
        SQLiteDataSource source = new SQLiteDataSource(sqlite);
        source.setUrl("jdbc:sqlite:" + path);
        HikariConfig pool = new HikariConfig();
        pool.setDataSource(source);
        pool.setMaximumPoolSize(1);
        pool.setMinimumIdle(1);
        pool.setConnectionTimeout(15000);
        pool.setPoolName("CqaSqlite");
        return new HikariDataSource(pool);
    }
    @Bean public TransactionTemplate writes(PlatformTransactionManager manager) { return new TransactionTemplate(manager); }
    @Bean(destroyMethod = "close") public ContractJson contractJson() { return new ContractJson(); }
    @Bean public ScoringEngine scoringEngine() { return new ScoringEngine(); }
}
