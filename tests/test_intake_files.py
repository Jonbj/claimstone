"""B7b: a file for one candidate is quarantined, checked by the engine's own gates, and counts
toward the floor only where the project declared that supplied copies do (F14).

Text extraction is faked except in one test, which runs the real `pdftotext` on a PDF built
here. Nothing is fetched.
"""

from __future__ import annotations

import shutil
import socket
import threading
from contextlib import contextmanager

import pytest

from claimstone import admissibility, control, flows, intake, operators
from claimstone.config import ConfigError, load_project
from tests.test_control import _cookie, _login, _request
from tests.test_portal_state import build_workspace

TITLE = "Information events and abnormal returns"


def _pdf(lines: list[str], pad: int = 12_000) -> bytes:
    """A real one-page PDF with the given text lines, padded past `min_pdf_bytes`."""
    content = "BT /F1 12 Tf 72 720 Td " + " ".join(f"({line}) Tj 0 -16 Td" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n%" + b"x" * pad + b"\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
            .encode())
    return out


@pytest.fixture()
def ws(tmp_path):
    projects_dir, store_dir, project, store = build_workspace(tmp_path)
    state = tmp_path / "state"
    operators.add_operator(state, "op1", "Op One", "correct horse")
    # A candidate of the bound round with no copy yet: what a supplied file is for.
    store.append("candidates.jsonl", {
        "candidate_key": "r1-c", "source_id": "S09", "round": "r1", "channel": "keyword",
        "source_class": "ACA", "title": TITLE, "doi": "10.1234/study.three",
        "url": "https://example.org/S09", "discovered_at": "2026-10-03T10:00:00+00:00"})
    flow_id = next(iter(flows.flows(store)))
    return {"projects": projects_dir, "store_dir": store_dir, "project": project,
            "store": store, "state": state, "flow_id": flow_id}


def _text_of(lines):
    return lambda _path: "\n".join(lines)


@contextmanager
def _served(ws, extract_text=None):
    httpd = control.make_server(ws["projects"], ws["store_dir"], host="127.0.0.1", port=0,
                                state_dir=ws["state"],
                                extract_text=extract_text or _text_of([TITLE]))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, headers, body = _login(base)
        assert status == 200
        yield base, _cookie(headers), body["csrf_token"], httpd.server_address[1]
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _upload(served, ws, payload: bytes, target="r1-c", content_type="application/pdf"):
    base, cookie, csrf, _port = served
    return _request(
        f"{base}/control/v1/p/{ws['project'].name}/flows/{ws['flow_id']}/intake/file"
        f"?target={target}", method="POST", raw_body=payload,
        headers={"Cookie": cookie, "Origin": base, "X-CSRF-Token": csrf,
                 "Content-Type": content_type})


def _supplied_rows(ws):
    return [row for row in ws["store"].read("acquisitions.jsonl")
            if row.get("provenance") == admissibility.OPERATOR_SUPPLIED]


def test_a_passing_file_is_reported_separately_by_default(ws):
    before = admissibility.rate(ws["store"], round_name="r1")
    with _served(ws) as served:
        status, _h, body = _upload(served, ws, _pdf([TITLE]))
    assert status == 201, body
    row = body["intake"]
    assert row["state"] == "REPORTED_SEPARATELY"
    assert row["links"]["candidate_key"] == "r1-c"
    assert row["links"]["identity"]["title_found"] is True
    [acquired] = _supplied_rows(ws)
    assert acquired["acquired"] is True and acquired["attempts"] == []
    assert acquired["licence"] is None  # unknown stays unknown
    assert acquired["intake_id"] == row["intake_id"]
    assert (ws["store"].root / "raw" / f"{acquired['sha256']}.pdf").exists()
    assert not (ws["store"].root / intake.QUARANTINE / f"{acquired['sha256']}.pdf").exists()

    after = admissibility.rate(ws["store"], round_name="r1")
    assert after["found"] == before["found"]             # the denominator never moves
    assert after["obtained"] == before["obtained"]       # separate: not in the numerator
    assert after["rate"] == before["rate"]
    assert after["supplied_separately"] == ["S09"]


def test_under_count_the_supplied_copy_enters_the_numerator(ws):
    with _served(ws) as served:
        assert _upload(served, ws, _pdf([TITLE]))[0] == 201
    separate = admissibility.rate(ws["store"], round_name="r1")
    counted = admissibility.rate(ws["store"], round_name="r1", supplied_copies="count")
    assert counted["found"] == separate["found"]
    assert counted["obtained"] == separate["obtained"] + 1
    assert counted["supplied_separately"] == []


def test_the_same_file_twice_is_one_copy_and_not_a_second_study(ws):
    payload = _pdf([TITLE])
    with _served(ws) as served:
        first = _upload(served, ws, payload)[2]["intake"]
        second = _upload(served, ws, payload)[2]["intake"]
    assert first["state"] == "REPORTED_SEPARATELY"
    assert second["state"] == "DUPLICATE" and "not a second study" in second["reason"]
    assert len(_supplied_rows(ws)) == 1


def test_a_file_whose_title_is_absent_is_a_possible_version_and_counts_for_nothing(ws):
    with _served(ws, extract_text=_text_of(["A different paper", "10.1234/study.three"])) as served:
        row = _upload(served, ws, _pdf(["A different paper"]))[2]["intake"]
    assert row["state"] == "POSSIBLE_VERSION"
    assert row["links"]["identity"] == {**row["links"]["identity"], "title_found": False,
                                        "doi_found": True}
    assert "(its DOI is)" in row["reason"]
    assert _supplied_rows(ws) == []
    assert (ws["store"].root / intake.QUARANTINE / f"{row['value']}.pdf").exists()


def test_a_file_that_is_not_a_document_is_rejected_by_the_content_gate(ws):
    with _served(ws) as served:
        row = _upload(served, ws, b"%PDF-1.4\n" + b"x" * 200 + b"\n%%EOF\n")[2]["intake"]
        not_pdf = _upload(served, ws, b"<html>" + b"x" * 20_000)[2]["intake"]
    assert row["state"] == "REJECTED" and "TOO_SHORT" in row["reason"]
    assert not_pdf["state"] == "REJECTED" and "NOT_TEXT" in not_pdf["reason"]
    assert _supplied_rows(ws) == []


def test_unreadable_text_is_rejected_at_identity(ws):
    def broken(_path):
        raise OSError("pdftotext missing")
    with _served(ws, extract_text=broken) as served:
        row = _upload(served, ws, _pdf([TITLE]))[2]["intake"]
    assert row["state"] == "REJECTED" and row["stage"] == "identity"
    assert _supplied_rows(ws) == []


def test_a_candidate_with_a_confirmed_copy_needs_no_supplied_one(ws):
    title = ws["store"].latest_by("candidates.jsonl", "candidate_key")["r1-a"]["title"]
    with _served(ws, extract_text=_text_of([title])) as served:
        row = _upload(served, ws, _pdf([title]), target="r1-a")[2]["intake"]
    assert row["state"] == "DUPLICATE" and "confirmed as a document" in row["reason"]
    assert _supplied_rows(ws) == []


def test_unknown_target_wrong_type_and_missing_target(ws):
    with _served(ws) as served:
        assert _upload(served, ws, _pdf([TITLE]), target="nope")[0] == 404
        assert _upload(served, ws, _pdf([TITLE]), content_type="text/plain")[0] == 415
        assert _upload(served, ws, _pdf([TITLE]), target="")[0] == 422
    assert list(ws["store"].read(intake.LEDGER)) == []


def test_an_oversized_declared_length_is_refused_before_any_byte_is_read(ws):
    with _served(ws) as served:
        base, cookie, csrf, port = served
        path = (f"/control/v1/p/{ws['project'].name}/flows/{ws['flow_id']}/intake/file"
                "?target=r1-c")
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall((f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                          f"Origin: {base}\r\nCookie: {cookie}\r\nX-CSRF-Token: {csrf}\r\n"
                          "Content-Type: application/pdf\r\n"
                          f"Content-Length: {intake.MAX_FILE_BYTES + 1}\r\n\r\n").encode())
            head = sock.recv(4096)
    assert b" 413 " in head.split(b"\r\n", 1)[0]
    assert list(ws["store"].read(intake.LEDGER)) == []
    assert list((ws["store"].root / intake.QUARANTINE).glob("*")) == []  # empty or absent


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")
def test_identity_is_read_by_the_real_pdftotext(ws):
    with _served(ws, extract_text=intake.pdf_text) as served:
        found = _upload(served, ws, _pdf([TITLE, "Working paper"]))[2]["intake"]
        missing = _upload(served, ws, _pdf(["Something else entirely"], pad=12_500))[2]["intake"]
    assert found["state"] == "REPORTED_SEPARATELY"
    assert missing["state"] == "POSSIBLE_VERSION"


# --- the policy is declared, and declaring it is drift ------------------------------------------


def test_supplied_copies_is_validated_and_enters_the_digest_only_when_declared(ws):
    root = ws["projects"] / ws["project"].name
    flow_row = flows.flows(ws["store"])[ws["flow_id"]]
    assert ws["project"].supplied_copies == "separate"
    assert flows.binding_state(ws["project"], ws["store"], flow_row)["state"] == "CURRENT"

    sources = root / "sources.yaml"
    original = sources.read_text(encoding="utf-8")
    sources.write_text(original + "\nsupplied_copies: sometimes\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="supplied_copies"):
        load_project(root)

    sources.write_text(original + "\nsupplied_copies: separate\n", encoding="utf-8")
    declared = load_project(root)
    assert declared.supplied_copies_declared
    # Declaring even the default is a protocol change: a flow bound before it now drifts.
    assert flows.binding_state(declared, ws["store"], flow_row)["state"] == "PROTOCOL_DRIFTED"

    sources.write_text(original + "\nsupplied_copies: count\n", encoding="utf-8")
    counted = load_project(root)
    assert counted.supplied_copies == "count"
    assert admissibility.admit(counted, ws["store"], round_name="r1")["supplied_copies"] == "count"
