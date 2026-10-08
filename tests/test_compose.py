"""The compose file and the code must name the same parser, and name it by digest.

Measured: `lfoppiano/grobid:latest-crf` produced 508 KB of TEI against `0.8.1`'s 91 KB on the same PDF. So
the image is an instrument, every corpus figure was measured with one of them, and two places naming it is
two places to disagree — the same shape as `cli.BACKENDS` against `runners.available()`.
"""

import pathlib
import re

import pytest

from claimstone import grobid

COMPOSE = pathlib.Path("compose.yaml")
pytestmark = pytest.mark.skipif(not COMPOSE.exists(), reason="no compose.yaml in this checkout")


def _compose_image() -> str:
    found = re.search(r"^\s+image:\s*(\S+)\s*$", COMPOSE.read_text(encoding="utf-8"), re.M)
    assert found, "compose.yaml declares no image"
    return found.group(1)


def test_the_compose_file_names_the_image_the_client_names():
    assert _compose_image().startswith(grobid.IMAGE + "@"), (
        f"compose.yaml pins {_compose_image()!r} and grobid.py names {grobid.IMAGE!r}"
    )


def test_the_image_is_pinned_by_digest_and_not_by_tag_alone():
    """A tag can be re-pushed under the same name. A digest cannot, and every corpus figure in
    DESIGN_DECISIONS.md was measured with one build of this parser."""
    assert re.search(r"@sha256:[0-9a-f]{64}$", _compose_image()), (
        f"{_compose_image()!r} is not pinned by digest"
    )


def test_the_digest_is_recorded_in_the_design_record():
    """Same rule as GATE_VERSION and CHUNK_VERSION: an instrument the record does not name is an
    instrument nobody can tell you changed."""
    digest = _compose_image().split("@")[1]
    record = pathlib.Path("docs/DESIGN_DECISIONS.md").read_text(encoding="utf-8")
    assert digest in record, f"{digest} is not named in docs/DESIGN_DECISIONS.md"


def _services() -> dict:
    import yaml

    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def test_the_engine_service_is_a_job_and_not_a_service():
    """A job with a restart policy is how a finished run becomes an infinite one. Checked on the
    `claimstone` service itself: the portal's `api` and `web` are long-running read models and do
    restart (D84), which a text search over the rest of the file used to mistake for the job."""
    engine = _services()["claimstone"]
    assert engine.get("profiles") == ["cli"], "the engine must not start with `compose up`"
    assert "restart" not in engine


def test_the_store_is_a_bind_mount_and_not_a_named_volume():
    """The named volume is the portable choice and the wrong one: the argument for append-only JSONL is
    that it is diffable and auditable with `grep`, which a volume makes require entering a container."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "- ./store:/app/store" in text
    assert "- ./projects:/app/projects" in text
    # A top-level `volumes:` key would mean a named volume was declared somewhere.
    assert not re.search(r"^volumes:", text, re.M)


def test_the_contact_address_is_required_from_the_environment():
    """The repository is public and the image may reach a registry, so it is never baked in. And the
    failure says what to do rather than surfacing inside the first request."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "CLAIMSTONE_CONTACT_EMAIL: ${CLAIMSTONE_CONTACT_EMAIL:?" in text


def test_the_parser_port_is_not_published():
    """Publishing 8070 would put an unauthenticated PDF parser on the LAN. The engine reaches it by
    service name on the private network. The only published port in the file is the portal's
    `web`, and only on the host's loopback (D84)."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "8070:8070" not in text
    services = _services()
    published = {name for name, service in services.items() if service.get("ports")}
    assert published == {"web"}, f"published ports on {sorted(published)}"
    for mapping in services["web"]["ports"]:
        assert str(mapping).startswith("127.0.0.1:"), f"{mapping!r} is not loopback-only"


def test_the_portal_api_is_read_only_isolated_and_secret_free():
    """D84: `api` mounts the ledgers read-only, sits only on a network with no egress, publishes
    nothing, shares the CLI job's image (one code identity, D42) and receives no secret value —
    only the word `present` for each configured key."""
    import yaml

    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    api = document["services"]["api"]
    assert "profiles" not in api  # started by a plain `docker compose up` (D110)
    assert "ports" not in api
    assert set(api["volumes"]) == {"./store:/app/store:ro", "./projects:/app/projects:ro"}
    assert api.get("read_only") is True
    assert api["networks"] == ["portal_internal"]
    assert document["networks"]["portal_internal"].get("internal") is True
    assert api["image"] == document["services"]["claimstone"]["image"]
    for name in ("CLAIMSTONE_CONTACT_EMAIL", "OLLAMA_API_KEY", "OPENALEX_API_KEY"):
        assert api["environment"][name] == "${%s:+present}" % name, name


def test_the_store_is_never_copied_into_the_image():
    """It holds the fetched bytes of copyrighted papers, which is why it is gitignored."""
    ignore = pathlib.Path(".dockerignore").read_text(encoding="utf-8")
    assert "store/" in ignore
    assert "projects/alembic-s4/" in ignore


# What the parser image actually contains, checked inside it once:
#   curl absent · wget absent · nc absent · python3 absent · perl at /usr/bin/perl
# The healthcheck shipped with `curl -fsS` and failed every probe with `curl: not found`, so the container
# was permanently unhealthy and `depends_on: service_healthy` refused to start the job — while GROBID was
# answering `true` throughout. A healthcheck written against tools the image lacks reports a broken parser
# that works, which is worse than having none.
ABSENT_FROM_THE_IMAGE = ("curl", "wget", "nc ", "python3", "python ")


def _healthcheck() -> str:
    """The probe command alone, with the comments stripped.

    The comments explain at length why `curl` is not used, so a test reading the whole block fails on the
    sentence describing the fix — the same error as grepping a module's source for the word "threshold"
    when its docstring is about not having one.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    start = text.index("healthcheck:")
    end = text.index("deploy:", start)
    lines = [
        line for line in text[start:end].splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return "\n".join(lines)


def test_the_healthcheck_uses_no_tool_the_parser_image_lacks():
    probe = _healthcheck()
    for tool in ABSENT_FROM_THE_IMAGE:
        assert tool not in probe, (
            f"the healthcheck calls {tool.strip()!r}, which this image does not have — "
            f"every probe would fail and the container would never become healthy"
        )


def test_the_healthcheck_asks_the_endpoint_the_client_asks():
    """Not a port check: a JVM that has bound 8070 and not yet loaded its models accepts the connection
    and answers nothing, which is exactly the state the wait exists to sit through."""
    probe = _healthcheck()
    assert "/api/isalive" in probe
    assert "true" in probe


def test_the_job_waits_on_the_condition_rather_than_on_a_guess():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "condition: service_healthy" in text
    # Same care: the comments discuss sleeping in order to rule it out.
    code = "\n".join(line for line in text.splitlines()
                     if line.strip() and not line.strip().startswith("#"))
    assert "sleep" not in code


def test_the_control_service_writes_only_what_it_must_and_publishes_nothing():
    """D89/B13: `control` is the write boundary. It shares the image (D42), publishes no port (the browser
    reaches it through `web`), writes the store and its own state but only reads the projects, cannot
    write credentials inside the container, and keeps `api` exactly as read-only as before."""
    import yaml

    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    control = document["services"]["control"]
    assert "profiles" not in control
    assert "ports" not in control
    assert control["image"] == document["services"]["claimstone"]["image"]
    assert set(control["volumes"]) == {"./store:/app/store", "./projects:/app/projects:ro",
                                       "./.claimstone:/app/.claimstone"}
    assert control.get("read_only") is True
    assert "portal_internal" in control["networks"]
    command = control["command"]
    assert command[command.index("--credentials-file") + 1] == "none"
    assert control["environment"]["OPENALEX_API_KEY"] == "${OPENALEX_API_KEY:+present}"
    web = document["services"]["web"]
    assert web["depends_on"]["control"]["condition"] == "service_healthy"
    assert ".claimstone/" in pathlib.Path(".dockerignore").read_text(encoding="utf-8")


def test_nginx_passes_origin_to_control_and_never_claims_https():
    conf = pathlib.Path("web/nginx/default.conf").read_text(encoding="utf-8")
    block = conf[conf.index("location /control/"):]
    block = block[:block.index("}") + 1]
    assert "proxy_pass http://control:8790;" in block
    assert 'proxy_set_header Origin ""' not in block       # the control server checks Origin
    assert 'proxy_set_header X-Forwarded-Proto "";' in block
    assert "limit_except GET POST" in block
