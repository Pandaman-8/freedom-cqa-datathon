package cqa.dataset;

import cqa.api.RequestBodies;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;
import static java.nio.file.LinkOption.NOFOLLOW_LINKS;
import static java.nio.file.StandardOpenOption.*;

/** Exact transport bytes, private and content-addressed; never served by an HTTP route. */
@Component
public class DatasetSourceStore {
    private final Path directory;
    public DatasetSourceStore(@Value("${cqa.dataset-source-dir:}") String configured,
            @Value("${cqa.db-path}") String database) {
        directory = configured.isBlank() ? Path.of(database).getParent().resolve("dataset-sources") : Path.of(configured);
    }

    public void save(byte[] bytes) {
        Path temporary = null;
        try {
            if (!directory.isAbsolute() || bytes.length == 0 || bytes.length > RequestBodies.DATASET_LIMIT)
                throw new IOException();
            Files.createDirectories(directory, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
            var owner = directory.getFileSystem().getUserPrincipalLookupService()
                .lookupPrincipalByName(System.getProperty("user.name"));
            if (!Files.isDirectory(directory, NOFOLLOW_LINKS) || !Files.getOwner(directory, NOFOLLOW_LINKS).equals(owner)
                    || !Files.getPosixFilePermissions(directory, NOFOLLOW_LINKS).equals(PosixFilePermissions.fromString("rwx------")))
                throw new IOException();
            String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
            Path target = directory.resolve(hash + ".dataset-source.json");
            if (!Files.exists(target, NOFOLLOW_LINKS)) {
                temporary = Files.createTempFile(directory, ".pending-", ".dataset-source.json",
                    PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
                try (var channel = FileChannel.open(temporary, WRITE)) {
                    var buffer = ByteBuffer.wrap(bytes);
                    while (buffer.hasRemaining()) channel.write(buffer);
                    channel.force(true);
                }
                // Atomic publication without overwriting an existing snapshot, even across processes.
                try { Files.createLink(target, temporary); }
                catch (FileAlreadyExistsException ignored) { /* Verify the concurrently published bytes below. */ }
                try (var channel = FileChannel.open(directory, READ)) { channel.force(true); }
            }
            if (!Files.isRegularFile(target, NOFOLLOW_LINKS) || !Files.getOwner(target, NOFOLLOW_LINKS).equals(owner)
                    || !Files.getPosixFilePermissions(target, NOFOLLOW_LINKS).equals(PosixFilePermissions.fromString("rw-------"))
                    || Files.size(target) != bytes.length || !Arrays.equals(Files.readAllBytes(target), bytes))
                throw new IOException();
        } catch (IOException | NoSuchAlgorithmException | UnsupportedOperationException | SecurityException e) {
            // Do not expose paths, customer bytes or filesystem exception causes.
            throw new IllegalStateException("Private dataset storage unavailable.");
        } finally {
            if (temporary != null) try { Files.deleteIfExists(temporary); } catch (IOException ignored) { }
        }
    }
}
