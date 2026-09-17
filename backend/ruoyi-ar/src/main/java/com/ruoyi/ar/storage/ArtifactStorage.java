package com.ruoyi.ar.storage;

import java.io.IOException;
import java.io.InputStream;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** File operations only. A committed file is not necessarily a published artifact. */
public interface ArtifactStorage {
    record Descriptor(UUID id, long bytes, String sha256) {
        public Descriptor {
            if (id == null || bytes < 0 || sha256 == null || !sha256.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("Expected UUID, nonnegative size and lowercase SHA256");
            }
        }

        public String storageKey() { return id + ".bin"; }
    }

    enum Phase { PARTIAL, STAGED, COMMITTED }
    record Entry(UUID id, Phase phase, long bytes, Instant modifiedAt) { }

    /** Streams and verifies input. Caller owns the input stream. Retry uses the same descriptor. */
    void stage(Descriptor expected, InputStream input) throws IOException;

    /** No overwrite. Repeating a successful commit with identical metadata is safe. */
    void commit(Descriptor expected) throws IOException;

    /** Recomputes size and digest; absence or corruption fails closed. */
    void verify(Descriptor expected) throws IOException;

    /** Caller must authorize access and close the returned stream. No HTTP exposure here. */
    InputStream open(UUID id) throws IOException;

    /** Permanently removes this ID's partial, staged and committed bytes; idempotent under the file lock. */
    void delete(UUID id) throws IOException;

    /** Operational inventory, not a database reconciliation or automatic cleanup. */
    List<Entry> inventory() throws IOException;
}
