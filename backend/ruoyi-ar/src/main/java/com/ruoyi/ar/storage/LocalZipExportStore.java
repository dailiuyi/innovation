package com.ruoyi.ar.storage;

import java.io.BufferedOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.DigestOutputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;
import java.util.UUID;

/** Private ZIP cache beside artifact storage. Not a user-visible directory. */
public final class LocalZipExportStore {
    public record Descriptor(UUID id, long bytes, String sha256) {}

    @FunctionalInterface
    public interface ZipWriter { void write(OutputStream out) throws IOException; }

    /** Buffer in front of the file write; coalesces the small chunks a ZIP writer emits. */
    static final int WRITE_BUFFER_BYTES = 64 * 1024;

    private final Path files;
    private final Path locks;

    /** Bulk writes must reach the next stream as one call; the JDK default writes byte by byte. */
    static class BulkOutputStream extends FilterOutputStream {
        BulkOutputStream(OutputStream out) { super(out); }
        @Override public void write(int b) throws IOException { out.write(b); }
        @Override public void write(byte[] b, int off, int len) throws IOException { out.write(b, off, len); }
    }

    /** Boundary stream for a writer that owns flushing: bulk writes pass through, close only flushes. */
    public static OutputStream keepOpen(OutputStream out) {
        Objects.requireNonNull(out);
        return new BulkOutputStream(out) {
            @Override public void close() throws IOException { flush(); }
        };
    }

    /** Counts every written byte and forwards bulk writes unchanged. */
    static final class CountingOutputStream extends BulkOutputStream {
        private final long[] count;
        CountingOutputStream(OutputStream out, long[] count) { super(out); this.count = count; }
        @Override public void write(int b) throws IOException { super.write(b); count[0]++; }
        @Override public void write(byte[] b, int off, int len) throws IOException { super.write(b, off, len); count[0] += len; }
    }

    public LocalZipExportStore(Path root) throws IOException {
        Path absolute = root.toAbsolutePath().normalize();
        directory(absolute);
        files = directory(absolute.resolve("zip-exports"));
        locks = directory(files.resolve("locks"));
    }

    private static Path directory(Path path) throws IOException {
        for (Path current = path; current != null; current = current.getParent()) {
            if (Files.isSymbolicLink(current)) throw new IOException("Storage directories cannot be symbolic links");
        }
        Files.createDirectories(path);
        if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Storage directory unavailable");
        return path;
    }

    private static Path file(Path directory, UUID id, String suffix) throws IOException {
        Path result = directory.resolve(Objects.requireNonNull(id).toString() + suffix);
        if (Files.exists(result, LinkOption.NOFOLLOW_LINKS)
                && !Files.isRegularFile(result, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Storage entry must be a regular file");
        }
        return result;
    }

    public Descriptor write(UUID id, ZipWriter writer) throws IOException {
        Objects.requireNonNull(writer);
        class Holder { Descriptor value; }
        Holder holder = new Holder();
        locked(id, () -> {
            Path target = file(files, id, ".zip");
            if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
                holder.value = existing(id, target);
                return;
            }
            Path partial = file(files, id, ".part");
            Files.deleteIfExists(partial);
            try {
                MessageDigest digest = sha256();
                long[] count = {0};
                try (FileChannel channel = FileChannel.open(partial, StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS);
                     OutputStream buffered = new BufferedOutputStream(Channels.newOutputStream(channel), WRITE_BUFFER_BYTES);
                     DigestOutputStream digestStream = new DigestOutputStream(buffered, digest);
                     OutputStream counted = new CountingOutputStream(digestStream, count)) {
                    writer.write(counted);
                    // The buffered tail must reach the file before force and the atomic move.
                    counted.flush();
                    channel.force(true);
                }
                Files.move(partial, target, StandardCopyOption.ATOMIC_MOVE);
                holder.value = new Descriptor(id, count[0], HexFormat.of().formatHex(digest.digest()));
            } catch (IOException | RuntimeException error) {
                try { Files.deleteIfExists(partial); } catch (IOException cleanup) { error.addSuppressed(cleanup); }
                throw error;
            }
        });
        return holder.value;
    }

    public InputStream open(UUID id, long offset, long length) throws IOException {
        Path path = file(files, id, ".zip");
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Zip missing");
        long size = Files.size(path);
        if (offset < 0 || length < 0 || offset > size || offset + length > size) throw new IOException("Invalid range");
        FileChannel channel = FileChannel.open(path, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS);
        channel.position(offset);
        return new LocalArtifactStorage.BoundedInputStream(Channels.newInputStream(channel), length);
    }

    public boolean exists(UUID id) throws IOException {
        return Files.isRegularFile(file(files, id, ".zip"), LinkOption.NOFOLLOW_LINKS);
    }

    public void delete(UUID id) throws IOException {
        locked(id, () -> {
            Files.deleteIfExists(file(files, id, ".part"));
            Files.deleteIfExists(file(files, id, ".zip"));
        });
    }

    public void deletePart(UUID id) throws IOException {
        locked(id, () -> Files.deleteIfExists(file(files, id, ".part")));
    }

    private Descriptor existing(UUID id, Path target) throws IOException {
        MessageDigest digest = sha256();
        long bytes = 0;
        try (InputStream in = Files.newInputStream(target, LinkOption.NOFOLLOW_LINKS)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = in.read(buffer)) != -1) { digest.update(buffer, 0, read); bytes += read; }
        }
        return new Descriptor(id, bytes, HexFormat.of().formatHex(digest.digest()));
    }

    private void locked(UUID id, IoOperation action) throws IOException {
        try (FileChannel channel = FileChannel.open(file(locks, id, ".lock"), StandardOpenOption.CREATE,
                StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
            try (FileLock lock = channel.tryLock()) {
                if (lock == null) throw new IOException("Artifact operation already in progress; retry later");
                action.run();
            } catch (OverlappingFileLockException error) {
                throw new IOException("Artifact operation already in progress; retry later", error);
            }
        }
    }

    private static MessageDigest sha256() {
        try { return MessageDigest.getInstance("SHA-256"); }
        catch (NoSuchAlgorithmException error) { throw new IllegalStateException(error); }
    }

    @FunctionalInterface
    private interface IoOperation { void run() throws IOException; }
}
