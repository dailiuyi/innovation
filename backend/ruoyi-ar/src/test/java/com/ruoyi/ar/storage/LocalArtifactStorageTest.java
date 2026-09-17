package com.ruoyi.ar.storage;

import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LocalArtifactStorageTest {
    @TempDir Path root;
    private static final byte[] DATA = "synthetic artifact; no client format assumed".getBytes(java.nio.charset.StandardCharsets.UTF_8);

    private ArtifactStorage.Descriptor descriptor(UUID id, byte[] data) throws Exception {
        return new ArtifactStorage.Descriptor(id, data.length,
                HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data)));
    }

    @Test void physicalDeleteRemovesAllPayloadsButPreservesOtherIdsAndLock() throws Exception {
        var storage = new LocalArtifactStorage(root, 1024);
        var selected = descriptor(UUID.randomUUID(), DATA);
        var other = descriptor(UUID.randomUUID(), DATA);
        storage.stage(selected, new ByteArrayInputStream(DATA));storage.commit(selected);
        storage.stage(other, new ByteArrayInputStream(DATA));storage.commit(other);
        Files.write(root.resolve("staging/" + selected.id() + ".part"), DATA);
        Files.write(root.resolve("staging/" + selected.id() + ".ready"), DATA);
        storage.delete(selected.id());storage.delete(selected.id());
        assertFalse(Files.exists(root.resolve("committed/" + selected.storageKey())));
        assertFalse(Files.exists(root.resolve("staging/" + selected.id() + ".part")));
        assertFalse(Files.exists(root.resolve("staging/" + selected.id() + ".ready")));
        assertTrue(Files.exists(root.resolve("locks/" + selected.id() + ".lock")));
        storage.verify(other);
    }

    @Test void physicalDeleteFailsClosedForNonRegularTargetsAndBusyLocks() throws Exception {
        var storage = new LocalArtifactStorage(root, 1024);
        var id = UUID.randomUUID();
        Path invalid = root.resolve("committed/" + id + ".bin");
        Files.createDirectory(invalid);
        Files.write(root.resolve("staging/" + id + ".part"), DATA);
        assertThrows(IOException.class, () -> storage.delete(id));
        assertTrue(Files.exists(root.resolve("staging/" + id + ".part")));
        Files.delete(invalid);
        try (var channel = FileChannel.open(root.resolve("locks/" + id + ".lock"), StandardOpenOption.WRITE);
             var lock = channel.lock()) {
            assertThrows(IOException.class, () -> storage.delete(id));
        }
        storage.delete(id);
    }

    @Test void stageIsPrivateAndCommitSurvivesRestart() throws Exception {
        var storage = new LocalArtifactStorage(root, 1024);
        var expected = descriptor(UUID.randomUUID(), DATA);
        storage.stage(expected, new ByteArrayInputStream(DATA));
        assertThrows(IOException.class, () -> storage.open(expected.id()));
        assertEquals(ArtifactStorage.Phase.STAGED, storage.inventory().getFirst().phase());
        storage.commit(expected);
        var restarted = new LocalArtifactStorage(root, 1024);
        restarted.verify(expected);
        try (var stream = restarted.open(expected.id())) { assertArrayEquals(DATA, stream.readAllBytes()); }
        assertEquals(ArtifactStorage.Phase.COMMITTED, restarted.inventory().getFirst().phase());
        assertEquals(expected.id() + ".bin", expected.storageKey());
    }

    @Test void idempotentRetriesNeverReplaceContent() throws Exception {
        var storage = new LocalArtifactStorage(root, 1024);
        var expected = descriptor(UUID.randomUUID(), DATA);
        storage.stage(expected, new ByteArrayInputStream(DATA));
        storage.stage(expected, new ByteArrayInputStream(DATA));
        storage.commit(expected);
        storage.commit(expected);
        storage.stage(expected, new ByteArrayInputStream(DATA));
        var conflicting = descriptor(expected.id(), "different".getBytes());
        assertThrows(IOException.class, () -> storage.stage(conflicting, new ByteArrayInputStream("different".getBytes())));
        assertThrows(IOException.class, () -> storage.commit(conflicting));
        storage.verify(expected);
    }

    @Test void sizeDigestAndConfiguredLimitRejectBeforeCommit() throws Exception {
        var storage = new LocalArtifactStorage(root, 1024);
        var expected = descriptor(UUID.randomUUID(), DATA);
        assertThrows(IOException.class, () -> storage.stage(expected, new ByteArrayInputStream(new byte[DATA.length])));
        assertThrows(IOException.class, () -> storage.stage(expected, new ByteArrayInputStream(new byte[DATA.length + 1])));
        assertThrows(IOException.class, () -> storage.stage(expected, new ByteArrayInputStream(new byte[1])));
        assertTrue(storage.inventory().isEmpty());
        assertThrows(IOException.class, () -> storage.commit(expected));
        assertThrows(IOException.class, () -> new LocalArtifactStorage(root, 1).stage(expected, new ByteArrayInputStream(DATA)));
    }

    @Test void interruptedInputCannotBecomeCommitted() throws Exception {
        var storage = new LocalArtifactStorage(root, 1024);
        var expected = descriptor(UUID.randomUUID(), DATA);
        InputStream failing = new InputStream() {
            private int calls;
            @Override public int read() throws IOException { throw new IOException("Injected transport failure"); }
            @Override public int read(byte[] bytes) throws IOException {
                if (calls++ == 0) { bytes[0] = DATA[0]; return 1; }
                throw new IOException("Injected transport failure");
            }
        };
        assertThrows(IOException.class, () -> storage.stage(expected, failing));
        assertTrue(storage.inventory().isEmpty());
        assertThrows(IOException.class, () -> storage.open(expected.id()));
        storage.stage(expected, new ByteArrayInputStream(DATA));
        storage.commit(expected);
        storage.verify(expected);
    }

    @Test void stalePartialIsVisibleAndCanBeRetriedAfterRestart() throws Exception {
        new LocalArtifactStorage(root, 1024);
        var expected = descriptor(UUID.randomUUID(), DATA);
        Files.write(root.resolve("staging/" + expected.id() + ".part"), new byte[] {1, 2});
        var restarted = new LocalArtifactStorage(root, 1024);
        assertEquals(ArtifactStorage.Phase.PARTIAL, restarted.inventory().getFirst().phase());
        restarted.stage(expected, new ByteArrayInputStream(DATA));
        restarted.commit(expected);
        restarted.verify(expected);
    }

    @Test void crashAfterLinkCreationIsRecoverable() throws Exception {
        var storage = new LocalArtifactStorage(root, 1024);
        var expected = descriptor(UUID.randomUUID(), DATA);
        storage.stage(expected, new ByteArrayInputStream(DATA));
        Files.createLink(root.resolve("committed/" + expected.storageKey()), root.resolve("staging/" + expected.id() + ".ready"));
        var restarted = new LocalArtifactStorage(root, 1024);
        assertEquals(2, restarted.inventory().size());
        restarted.commit(expected);
        assertEquals(1, restarted.inventory().size());
        restarted.verify(expected);
    }

    @Test void detectsSameLengthCorruption() throws Exception {
        var storage = new LocalArtifactStorage(root, 1024);
        var expected = descriptor(UUID.randomUUID(), DATA);
        storage.stage(expected, new ByteArrayInputStream(DATA));
        storage.commit(expected);
        Files.write(root.resolve("committed/" + expected.storageKey()), new byte[DATA.length]);
        assertThrows(IOException.class, () -> storage.verify(expected));
        assertThrows(IOException.class, () -> storage.commit(expected));
    }

    @Test void concurrentWriterReceivesRetryableFailure() throws Exception {
        var storage = new LocalArtifactStorage(root, 1024);
        var expected = descriptor(UUID.randomUUID(), DATA);
        try (var channel = FileChannel.open(root.resolve("locks/" + expected.id() + ".lock"),
                StandardOpenOption.CREATE, StandardOpenOption.WRITE); var lock = channel.lock()) {
            assertThrows(IOException.class, () -> storage.stage(expected, new ByteArrayInputStream(DATA)));
        }
        storage.stage(expected, new ByteArrayInputStream(DATA));
        storage.commit(expected);
    }

    @Test void invalidDescriptorCannotIntroducePaths() {
        assertThrows(IllegalArgumentException.class, () -> new ArtifactStorage.Descriptor(null, 1, "../file"));
        assertThrows(IllegalArgumentException.class, () -> new ArtifactStorage.Descriptor(UUID.randomUUID(), -1, "0".repeat(64)));
        assertThrows(IllegalArgumentException.class, () -> new LocalArtifactStorage(root, 0));
    }

    @Test void nonRegularEntriesFailClosed() throws Exception {
        var storage = new LocalArtifactStorage(root, 1024);
        var expected = descriptor(UUID.randomUUID(), DATA);
        Files.createDirectory(root.resolve("committed/" + expected.storageKey()));
        assertThrows(IOException.class, () -> storage.open(expected.id()));
        assertThrows(IOException.class, () -> storage.commit(expected));
        assertThrows(IOException.class, storage::inventory);
    }
}
