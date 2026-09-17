"""Packaging extension point only. No default format or AR loader is selected.

This development-tool boundary is independent of HTTP, storage and business tables.
Implementations own their file layout and manifest, and must not expose incomplete
outputs as successful results. Client agreement is required before implementing one.
"""
from pathlib import Path
from typing import Protocol


class PackageCodec(Protocol):
    """Optional production-tool adapter; never infer a codec from a file extension.

    source can be a file or directory, as agreed by the concrete adapter.
    A runtime-native file may need no codec at all: transport accepts raw bytes.
    Both operations reject existing destinations and report failures by exception.
    Implementations must document limits and clean up their incomplete outputs.
    """

    def pack(self, source: Path, destination: Path) -> None:
        """Create a complete deliverable in a new destination path."""
        ...

    def unpack(self, source: Path, destination: Path, *, max_bytes: int) -> None:
        """Materialize a verified deliverable into a new bounded destination.

        An implementation must enforce safe relative paths, reject unsupported
        links and prevent writes outside destination. AR loading is out of scope.
        """
        ...
