#!/usr/bin/env python
"""Write `docs/contracts/portal-api.schema.json` from `claimstone.api_schema`.

The schema is hand-declared in the package (see that module for why); this tool only renders
and commits it, so the file on disk is always exactly the declaration. `tests/test_api_contract.py`
re-renders it in memory and compares, byte for byte, so a stale committed schema fails the
checks instead of misleading the frontend's type generation (spec §3.4).

Run it from the repository root:

    .venv/bin/python tools/build_portal_api_schema.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from claimstone import api_schema  # noqa: E402

TARGET = pathlib.Path(__file__).resolve().parent.parent / "docs" / "contracts" / \
    "portal-api.schema.json"


def render() -> str:
    """The canonical file text: one JSON document, sorted keys, one-space indent, trailing
    newline. Sorted keys so a re-render never produces a spurious diff."""
    return json.dumps(api_schema.document(), ensure_ascii=False, indent=1,
                      sort_keys=True) + "\n"


def main() -> int:
    text = render()
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(TARGET.parent.parent)} "
          f"({len(text.encode('utf-8'))} bytes, {len(api_schema.ROUTES)} routes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
