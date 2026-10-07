"""The CLI's own signature: it declares its class, and it cannot claim an operator id.

`adjudicate` is the only verdict-producing call, so the row the CLI writes is the record
of what happened — and what happened is a person at a terminal declaring a name, not a
portal session authenticating one (B3, F16).
"""

from claimstone import cli, synthesize
from tests.test_portal_state import build_workspace

RATIONALE = "r" * 130


def test_a_cli_signature_declares_itself_and_carries_no_actor(tmp_path):
    projects_dir, store_dir, project, store = build_workspace(tmp_path)
    question = next(q for q in project.questions if q.kind != "operational")
    stored = synthesize.latest_profiles(store, round_name="r1")[question.id]
    rationale = tmp_path / "rationale.txt"
    rationale.write_text(RATIONALE, encoding="utf-8")
    code = cli.main(["adjudicate", str(projects_dir / project.name), question.id,
                     "--round", "r1",
                     "--verdict", "UNANSWERED_IN_LITERATURE",
                     "--rationale-file", str(rationale), "--by", "a person",
                     "--profile-sha256", stored["profile_sha256"],
                     "--store", str(store_dir)])
    assert code == 0
    row = list(store.read(synthesize.ADJUDICATIONS))[-1]
    assert row["adjudication_version"] == 2
    assert row["signer_auth"] == "cli-declared"
    assert row["actor"] is None


def test_the_cli_refuses_to_sign_a_stale_hash_like_the_engine_does(tmp_path):
    """The CLI adds no rule of its own: the engine's StaleProfile reaches the terminal
    unchanged, and nothing is written."""
    projects_dir, store_dir, project, store = build_workspace(tmp_path)
    question = next(q for q in project.questions if q.kind != "operational")
    rationale = tmp_path / "rationale.txt"
    rationale.write_text(RATIONALE, encoding="utf-8")
    code = cli.main(["adjudicate", str(projects_dir / project.name), question.id,
                     "--round", "r1",
                     "--verdict", "SUPPORTED",
                     "--rationale-file", str(rationale), "--by", "a person",
                     "--profile-sha256", "0" * 64,
                     "--store", str(store_dir)])
    assert code == 2
    assert list(store.read(synthesize.ADJUDICATIONS)) == []