package com.ruoyi.ar.storage;

import static org.junit.jupiter.api.Assertions.*;

import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.DigestOutputStream;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Random;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Times the same ZIP package through three write chains: the complete pre-fix store chain (unbuffered
 * file channel plus a boundary stream that only overrode {@code close()}), the same chain with only the
 * boundary replaced, and the fixed chain. Host acceptance raises the sample with
 * {@code -Dzip.benchmark.miB=250 -Dzip.benchmark.runs=1} and records the printed lines; the default keeps
 * the routine module test short. No timing threshold is asserted and no ratio here promises an
 * end-to-end speedup.
 */
class ZipWriteBenchmarkTest {
    private static final int DEFAULT_SAMPLE_MIB = 8;
    private static final int ENTRY_MIB = 4;
    private static final long MIB = 1024L * 1024L;
    private static final String LEGACY_FULL = "legacy-full";
    private static final String LEGACY_BOUNDARY = "legacy-boundary";
    private static final String FIXED = "fixed";
    private static final List<String> VARIANTS = List.of(LEGACY_FULL, LEGACY_BOUNDARY, FIXED);

    @TempDir Path root;

    @Test void writeChainsAreMeasuredAndProduceTheSameEntries() throws Exception {
        int sampleMiB = Integer.getInteger("zip.benchmark.miB", DEFAULT_SAMPLE_MIB);
        int runs = Integer.getInteger("zip.benchmark.runs", 1);
        assertTrue(sampleMiB > 0 && runs > 0, "Benchmark sample size and run count must be positive");
        long sampleBytes = sampleMiB * MIB;
        byte[] block = incompressible((int) Math.min(ENTRY_MIB * MIB, sampleBytes));
        var store = new LocalZipExportStore(root);
        print("{\"environment\":{\"java\":\"" + System.getProperty("java.version") + "\",\"os\":\""
                + System.getProperty("os.name") + " " + System.getProperty("os.arch") + "\",\"processors\":"
                + Runtime.getRuntime().availableProcessors() + ",\"maxHeapBytes\":"
                + Runtime.getRuntime().maxMemory() + ",\"sampleMiB\":" + sampleMiB + ",\"entryMiB\":"
                + ENTRY_MIB + ",\"runs\":" + runs + ",\"variants\":\"" + String.join(",", VARIANTS) + "\"}}");
        for (String variant : VARIANTS) {
            for (int run = 1; run <= runs; run++) {
                UUID id = UUID.randomUUID();
                long started = System.nanoTime();
                long fileBytes;
                String digest;
                Path published;
                if (LEGACY_FULL.equals(variant)) {
                    published = writeWithPreFixChain(id, block, sampleBytes);
                    fileBytes = Files.size(published);
                    digest = sha256(published);
                } else {
                    var descriptor = store.write(id, out -> pack(LEGACY_BOUNDARY.equals(variant)
                            ? byteAtATimeKeepOpen(out) : LocalZipExportStore.keepOpen(out), block, sampleBytes));
                    published = root.resolve("zip-exports/" + id + ".zip");
                    fileBytes = descriptor.bytes();
                    digest = descriptor.sha256();
                }
                long millis = (System.nanoTime() - started) / 1_000_000L;
                assertEquals(sampleBytes, readEntries(published), variant + " entry payload");
                assertEquals(Files.size(published), fileBytes, variant + " byte count");
                assertEquals(sha256(published), digest, variant + " digest");
                print("{\"variant\":\"" + variant + "\",\"run\":" + run + ",\"millis\":" + millis
                        + ",\"sampleBytes\":" + sampleBytes + ",\"fileBytes\":" + fileBytes
                        + ",\"sha256\":\"" + digest + "\"}");
            }
        }
    }

    private static void pack(OutputStream boundary, byte[] block, long sampleBytes) throws IOException {
        try (ZipOutputStream zip = new ZipOutputStream(boundary, StandardCharsets.UTF_8)) {
            long remaining = sampleBytes;
            int index = 0;
            while (remaining > 0) {
                int size = (int) Math.min(block.length, remaining);
                zip.putNextEntry(new ZipEntry("scene/models/chunk-" + index + ".bin"));
                zip.write(block, 0, size);
                zip.closeEntry();
                remaining -= size;
                index++;
            }
        }
    }

    /** Replays the pre-fix store chain: no buffering, and only {@code close()} overridden on the boundary. */
    private Path writeWithPreFixChain(UUID id, byte[] block, long sampleBytes) throws Exception {
        Path directory = root.resolve("zip-exports");
        Files.createDirectories(directory);
        Path partial = directory.resolve(id + ".part");
        Path target = directory.resolve(id + ".zip");
        try (FileChannel channel = FileChannel.open(partial, StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);
             OutputStream raw = Channels.newOutputStream(channel);
             DigestOutputStream digestStream = new DigestOutputStream(raw, MessageDigest.getInstance("SHA-256"));
             OutputStream counted = new FilterOutputStream(digestStream) {
                 @Override public void write(int b) throws IOException { out.write(b); }
                 @Override public void write(byte[] b, int off, int len) throws IOException { out.write(b, off, len); }
             }) {
            pack(byteAtATimeKeepOpen(counted), block, sampleBytes);
            channel.force(true);
        }
        Files.move(partial, target, StandardCopyOption.ATOMIC_MOVE);
        return target;
    }

    /** The pre-fix boundary stream: bulk writes degrade to single bytes because only close() is overridden. */
    private static OutputStream byteAtATimeKeepOpen(OutputStream out) {
        return new FilterOutputStream(out) {
            @Override public void close() throws IOException { flush(); }
        };
    }

    private static long readEntries(Path file) throws IOException {
        long bytes = 0;
        try (ZipFile archive = new ZipFile(file.toFile())) {
            var entries = archive.entries();
            while (entries.hasMoreElements()) {
                try (InputStream in = archive.getInputStream(entries.nextElement())) {
                    bytes += in.transferTo(OutputStream.nullOutputStream());
                }
            }
        }
        return bytes;
    }

    private static String sha256(Path file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(file)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = in.read(buffer)) != -1) digest.update(buffer, 0, read);
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static byte[] incompressible(int size) {
        byte[] data = new byte[size];
        new Random(20260920L + size).nextBytes(data);
        return data;
    }

    private static void print(String json) {
        System.out.println("ZIPBENCH " + json);
    }
}
