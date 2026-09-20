package com.ruoyi.ar.storage;

import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Random;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** The ZIP write chain must keep bulk writes intact, flush its tail, and publish only complete files. */
class LocalZipExportStoreTest {
    @TempDir Path root;

    /** Records how the next stream is written so byte-at-a-time degradation is visible. */
    private static final class RecordingOutputStream extends OutputStream {
        long bytes;
        int bulkCalls;
        int singleByteWrites;
        int largestChunk;
        boolean closed;

        @Override public void write(int b) { singleByteWrites++; bytes++; }
        @Override public void write(byte[] b, int off, int len) { bulkCalls++; largestChunk = Math.max(largestChunk, len); bytes += len; }
        @Override public void close() { closed = true; }
    }

    private static byte[] incompressible(int size) {
        byte[] data = new byte[size];
        new Random(13L * size).nextBytes(data);
        return data;
    }

    private static Path zipPath(Path root, UUID id, String suffix) {
        return root.resolve("zip-exports/" + id + suffix);
    }

    @Test void keepOpenForwardsBulkWritesAndFlushesInsteadOfClosing() throws Exception {
        var sink = new RecordingOutputStream();
        byte[] bulk = new byte[3 * LocalZipExportStore.WRITE_BUFFER_BYTES + 7];
        try (OutputStream keepOpen = LocalZipExportStore.keepOpen(sink)) {
            keepOpen.write(bulk);
            keepOpen.write(9);
            assertEquals(bulk.length + 1, sink.bytes);
        }
        assertEquals(1, sink.bulkCalls);
        assertEquals(bulk.length, sink.largestChunk);
        assertEquals(1, sink.singleByteWrites);
        assertFalse(sink.closed);
    }

    @Test void countingStreamCountsEveryByteWithoutSplittingBulkWrites() throws Exception {
        var sink = new RecordingOutputStream();
        long[] count = {0};
        OutputStream counted = new LocalZipExportStore.CountingOutputStream(sink, count);
        byte[] bulk = new byte[5 * LocalZipExportStore.WRITE_BUFFER_BYTES];
        counted.write(bulk, 0, bulk.length);
        counted.write(7);
        assertEquals(bulk.length + 1, count[0]);
        assertEquals(bulk.length + 1, sink.bytes);
        assertEquals(1, sink.bulkCalls);
        assertEquals(bulk.length, sink.largestChunk);
        assertEquals(1, sink.singleByteWrites);
    }

    @Test void zipPackageKeepsBytesDigestEntriesAndReuse() throws Exception {
        var store = new LocalZipExportStore(root);
        UUID id = UUID.randomUUID();
        byte[] payload = incompressible(2 * 1024 * 1024 + 12345);
        byte[] head = Arrays.copyOf(payload, payload.length / 3);
        var descriptor = store.write(id, out -> {
            try (ZipOutputStream zip = new ZipOutputStream(LocalZipExportStore.keepOpen(out), StandardCharsets.UTF_8)) {
                zip.putNextEntry(new ZipEntry("场景A/models/one.bin"));
                zip.write(payload);
                zip.closeEntry();
                zip.putNextEntry(new ZipEntry("场景A/models/two.bin"));
                zip.write(head);
                zip.closeEntry();
            }
        });
        Path published = zipPath(root, id, ".zip");
        byte[] bytes = Files.readAllBytes(published);
        assertEquals(bytes.length, descriptor.bytes());
        assertEquals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)), descriptor.sha256());
        assertEquals(bytes.length, store.open(id, 0, descriptor.bytes()).readAllBytes().length);
        assertFalse(Files.exists(zipPath(root, id, ".part")));
        try (ZipFile archive = new ZipFile(published.toFile())) {
            assertEquals(Set.of("场景A/models/one.bin", "场景A/models/two.bin"),
                    archive.stream().map(ZipEntry::getName).collect(Collectors.toSet()));
            assertArrayEquals(payload, archive.getInputStream(archive.getEntry("场景A/models/one.bin")).readAllBytes());
            assertArrayEquals(head, archive.getInputStream(archive.getEntry("场景A/models/two.bin")).readAllBytes());
        }
        var reused = store.write(id, out -> { throw new IOException("must reuse the published zip"); });
        assertEquals(descriptor.bytes(), reused.bytes());
        assertEquals(descriptor.sha256(), reused.sha256());
    }

    @Test void failedWritePublishesNothingAndLeavesNoPartialFile() throws Exception {
        var store = new LocalZipExportStore(root);
        UUID id = UUID.randomUUID();
        var error = assertThrows(IOException.class, () -> store.write(id, out -> {
            out.write(new byte[LocalZipExportStore.WRITE_BUFFER_BYTES + 11]);
            throw new IOException("synthetic disk failure");
        }));
        assertEquals("synthetic disk failure", error.getMessage());
        assertFalse(store.exists(id));
        assertFalse(Files.exists(zipPath(root, id, ".part")));
        assertFalse(Files.exists(zipPath(root, id, ".zip")));
    }
}
