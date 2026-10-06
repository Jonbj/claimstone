"""portal fixtures currency: the committed `web/tests/fixtures/*.json` are exactly what
`tools/build_portal_fixtures.py` regenerates (spec §3.4).

The fixtures are the frontend's test data, so a stale one must fail here — not mislead
vitest. The comparison is byte for byte: the tool pins every timestamp the build would
stamp "now", so a diff is a meaning change, never a re-run.
"""

from __future__ import annotations

import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
TARGET = REPO / "web" / "tests" / "fixtures"


def _tool():
    spec = importlib.util.spec_from_file_location(
        "build_portal_fixtures", REPO / "tools" / "build_portal_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_committed_fixtures_equal_the_regeneration():
    expected = _tool().snapshot()
    assert expected, "the tool regenerates nothing"
    committed = {str(path.relative_to(TARGET)): path.read_text(encoding="utf-8")
                 for path in sorted(TARGET.rglob("*.json"))}
    assert sorted(committed) == sorted(expected), (
        "stale fixture set; regenerate with "
        "'.venv/bin/python tools/build_portal_fixtures.py'")
    for name in sorted(expected):
        assert committed[name] == expected[name], f"stale fixture: {name}"