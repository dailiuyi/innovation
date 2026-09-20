package com.ruoyi.ar.storage;

import static org.junit.jupiter.api.Assertions.*;

import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
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
 * Times the same ZIP package through the fixed bulk-write boundary and through the pre-fix boundary that
 * only overrode {@code close()}. Host acceptance raises the sample with
 * {@code -Dzip.benchmark.miB=250 -Dzip.benchmark.runs=1} and records the printed lines; the default keeps
 * the routine module test fast. No timing threshold is asserted and no ratio here promises end-to-end speedup.
 */
class ZipWriteBenchmarkTest {
    private static final int DEFAULT_SAMPLE_MIB = 16;
    private static final int ENTRY_MIB = 4;
    private static final long MIB = 1024L * 1024L;

    @TempDir Path root;

    @Test void bulkWriteBoundaryIsMeasuredAgainstTheByteAtATimeWrapper() throws Exception {
        int sampleMiB = Integer.getInteger("zip.benchmark.miB", DEFAULT_SAMPLE_MIB);
        int runs = Integer.getInteger("zip.benchmark.runs", 1);
        assertTrue(sampleMiB > 0 && runs > 0, "Benchmark sample size and run count must be positive");
        long sampleBytes = sampleMiB * MIB;
        byte[] block = incompressible((int) Math.min(ENTRY_MIB * MIB, sampleBytes));
        var store = new LocalZipExportStore(root);
        print("{\"environment\":{\"java\":\"" + System.getProperty("java.version") + "\",\"os\":\""
                + System.getProperty("os.name") + " " + System.getProperty("os.arch") + "\",\"processors\":"
                + Runtime.getRuntime().availableProcessors() + ",\"maxHeapBytes\":" + Runtime.getRuntime().maxMemory()
                + ",\"sampleMiB\":" + sampleMiB + ",\"entryMiB\":" + ENTRY_MIB + ",\"runs\":" + runs + "}}");
        for (String variant : List.of("legacy", "fixed")) {
            for (int run = 1; run <= runs; run++) {
                UUID id = UUID.randomUUID();
                long started = System.nanoTime();
                var descriptor = store.write(id, out -> pack("legacy".equals(variant) ? byteAtATimeKeepOpen(out)
                        : LocalZipExportStore.keepOpen(out), block, sampleBytes));
                long millis = (System.nanoTime() - started) / 1_000_000L;
                Path published = root.resolve("zip-exports/" + id + ".zip");
                assertEquals(sampleBytes, readEntries(published), variant + " entry payload");
                assertEquals(Files.size(published), descriptor.bytes(), variant + " byte count");
                assertEquals(sha256(published), descriptor.sha256(), variant + " digest");
                print("{\"variant\":\"" + variant + "\",\"run\":" + run + ",\"millis\":" + millis
                        + ",\"sampleBytes\":" + sampleBytes + ",\"fileBytes\":" + descriptor.bytes()
                        + ",\"sha256\":\"" + descriptor.sha256() + "\"}");
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
