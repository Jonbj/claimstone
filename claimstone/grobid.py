"""The GROBID container, over HTTP.

Consolidation is off. Resolving 803 references through Crossref is not this stage's job — stage 3 is
otherwise pure local parsing, and which references become candidates is a decision belonging to
`discover`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_URL = "http://localhost:8070"

# The image every corpus figure was measured with. `latest-crf` is not a lighter drop-in: measured
# on the same PDF it produced 508 KB of TEI against 91 KB, so switching images would silently change
# body characters, sections and references. tools/check_instrument_versions.py holds it to this.
IMAGE = "lfoppiano/grobid:0.8.1"

START_COMMAND = (
    "  docker run -d --name claimstone-grobid -p 8070:8070 \\\n"
    f"    -e JAVA_TOOL_OPTIONS=-XX:-UseContainerSupport {IMAGE}"
)

# Measured 2026-09-24: without the flag the image's JVM dies at startup on this machine with
# "CgroupV2Subsystem.getInstance … anyController is null". Twenty minutes to find; one line to
# pass on.
WORKAROUND_NOTE = (
    "JAVA_TOOL_OPTIONS is required: the image's JVM cannot read cgroup v2 under\n"
    "Docker 29 and the container dies at startup."
)


class GrobidUnavailable(RuntimeError):
    """The server is not answering, with instructions rather than a bare timeout."""


class GrobidFailed(RuntimeError):
    """The server answered, and refused."""


def _default_transport() -> Any:
    import requests

    return requests


@dataclass
class Grobid:
    url: str = DEFAULT_URL
    timeout_s: int = 300
    transport: Any = field(default_factory=_default_transport)

    def is_alive(self) -> bool:
        try:
            response = self.transport.get(f"{self.url}/api/isalive", timeout=10)
        except Exception:
            return False
        return getattr(response, "status_code", 0) == 200

    def _unavailable(self) -> GrobidUnavailable:
        return GrobidUnavailable(
            f"GROBID is not answering on {self.url}.\nStart it with:\n{START_COMMAND}\n"
            f"{WORKAROUND_NOTE}"
        )

    def full_text(self, pdf: bytes, *, filename: str = "document.pdf") -> bytes:
        """PDF bytes in, TEI bytes out. Raises rather than returning something unusable."""
        if not self.is_alive():
            raise self._unavailable()
        try:
            response = self.transport.post(
                f"{self.url}/api/processFulltextDocument",
                files={"input": (filename, pdf, "application/pdf")},
                data={"consolidateHeader": "0", "consolidateCitations": "0"},
                timeout=self.timeout_s,
            )
        except Exception as exc:
            raise self._unavailable() from exc

        status = getattr(response, "status_code", 0)
        if status != 200:
            raise GrobidFailed(
                f"GROBID returned {status}: {getattr(response, 'text', '')[:200]}"
            )
        return response.content
