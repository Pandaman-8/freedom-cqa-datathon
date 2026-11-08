package cqa.dataset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.util.HexFormat;
import static org.junit.jupiter.api.Assertions.*;

class DatasetSourceStoreTest {
    @TempDir Path temp;
    private final byte[] bytes = " {\n \"synthetic\": \"Қ / é / 😀\"\n } \r\n".getBytes(StandardCharsets.UTF_8);
    private Path stored(Path directory) throws Exception {
        return directory.resolve(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)) + ".dataset-source.json");
    }
    @Test void exactBytesPrivatePermissionsIdempotencyAndRestart() throws Exception {
        Path directory = temp.resolve("dataset-sources");
        var store = new DatasetSourceStore("", temp.resolve("test.sqlite").toString());
        store.save(bytes); store.save(bytes);
        new DatasetSourceStore("", temp.resolve("test.sqlite").toString()).save(bytes);
        assertArrayEquals(bytes, Files.readAllBytes(stored(directory)));
        assertEquals(PosixFilePermissions.fromString("rw-------"), Files.getPosixFilePermissions(stored(directory)));
        assertEquals(PosixFilePermissions.fromString("rwx------"), Files.getPosixFilePermissions(directory));
        try (var files = Files.list(directory)) { assertEquals(1, files.count()); }
    }
    @Test void explicitDirectoryAndDistinctTransportBytesRemainDistinct() throws Exception {
        var directory = temp.resolve("private/archive");
        var store = new DatasetSourceStore(directory.toString(), temp.resolve("db.sqlite").toString());
        store.save(bytes); store.save("{}".getBytes(StandardCharsets.UTF_8));
        assertArrayEquals(bytes, Files.readAllBytes(stored(directory)));
        try (var files = Files.list(directory)) { assertEquals(2, files.count()); }
    }
    @Test void corruptExistingSnapshotIsNeverOverwritten() throws Exception {
        var store = new DatasetSourceStore("", temp.resolve("db.sqlite").toString()); store.save(bytes);
        Path target = stored(temp.resolve("dataset-sources")); Files.writeString(target, "tampered");
        assertThrows(IllegalStateException.class, () -> store.save(bytes));
        assertEquals("tampered", Files.readString(target));
    }
    @Test void insecureDirectoryAndRelativeConfigFailClosed() throws Exception {
        Path directory = Files.createDirectory(temp.resolve("public"));
        Files.setPosixFilePermissions(directory, PosixFilePermissions.fromString("rwxr-xr-x"));
        assertThrows(IllegalStateException.class, () -> new DatasetSourceStore(directory.toString(), "unused").save(bytes));
        assertThrows(IllegalStateException.class, () -> new DatasetSourceStore("relative", "unused").save(bytes));
        try (var files = Files.list(directory)) { assertEquals(0, files.count()); }
    }
    @Test void symlinkedDirectoryAndFileFailClosed() throws Exception {
        Path real = Files.createDirectory(temp.resolve("real"));
        Path link = Files.createSymbolicLink(temp.resolve("link"), real);
        assertThrows(IllegalStateException.class, () -> new DatasetSourceStore(link.toString(), "unused").save(bytes));
        var store = new DatasetSourceStore("", temp.resolve("db.sqlite").toString()); store.save(bytes);
        Path target = stored(temp.resolve("dataset-sources")); Files.delete(target);
        Path outside = Files.write(temp.resolve("outside"), bytes); Files.createSymbolicLink(target, outside);
        assertThrows(IllegalStateException.class, () -> store.save(bytes));
        assertArrayEquals(bytes, Files.readAllBytes(outside));
    }
}
