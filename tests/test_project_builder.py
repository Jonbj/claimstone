"""The project builder: no domain knowledge, no network, one atomic write."""

from __future__ import annotations

import pathlib

import pytest

from claimstone import project_builder as pb

REPO = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates" / "project"


def test_the_shipped_template_loads_and_lists():
    template = pb.load_template(TEMPLATES, "general")
    assert template["id"] == "general"
    assert [c["id"] for c in template["classes"]][:2] == ["ACA", "WP"]
    assert "sci-hub.se" in template["excluded_hosts"]
    assert [t["id"] for t in pb.list_templates(TEMPLATES)] == ["general"]


@pytest.mark.parametrize("bad", ["", "../etc/passwd", "General", "a" * 41, "no-such-template"])
def test_an_unknown_or_unsafe_template_id_is_refused(bad):
    with pytest.raises(pb.DraftInvalid) as raised:
        pb.load_template(TEMPLATES, bad)
    assert raised.value.problems[0].path == "template"
