"""Drive the new-project routes end to end against a throwaway workspace and validate the result.

Run it after changing the wizard's backend:

    .venv/bin/python tools/check_new_project_wizard.py

It builds a temporary `projects/`, `store/` and `templates/`, starts the control server in-process,
signs in as a temporary operator, saves the three steps, previews, creates the project, then loads the
created directory with `config.load_project` and compares its protocol digest with the preview's.
Nothing under the real `projects/` or `store/` is touched, and no network request is made.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from claimstone import control, flows, operators  # noqa: E402
from claimstone.config import load_project  # noqa: E402

STEPS = {
    1: {"name": "wizard-check", "description": "A throwaway project.",
        "topics": [{"label": "A topic", "terms": ["first search term", "second search term"]}]},
    2: {"questions": [{"text": "Does the effect exist?", "kind": "effect"},
                      {"text": "Which datasets cover the period?", "kind": "operational"}]},
    3: {"template": "general", "classes": ["ACA", "WP"], "acquisition_floor": 0.8,
        "floor_rationale": "Set before the first measured round, so no result can move it.",
        "supplied_copies": "separate", "notation": "none", "custom_value_labels": [],
        "extra_excluded_hosts": []},
}


def call(base, cookie, csrf, method, path, payload=None):
    headers = {"Cookie": cookie, "Origin": base, "X-CSRF-Token": csrf, "Content-Type": "application/json"}
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(f"{base}/control/v1{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as raised:
        return raised.code, json.loads(raised.read())


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "projects").mkdir()
        shutil.copytree(REPO / "templates", root / "templates")
        operators.add_operator(root / "state", "check", "Wizard check", "correct horse")
        httpd = control.make_server(root / "projects", root / "store", host="127.0.0.1", port=0,
                                    state_dir=root / "state")
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            login = urllib.request.Request(
                f"{base}/control/v1/session", method="POST", headers={"Origin": base, "Content-Type": "application/json"},
                data=json.dumps({"id": "check", "password": "correct horse"}).encode())
            with urllib.request.urlopen(login, timeout=10) as response:
                cookie = response.headers["Set-Cookie"].split(";")[0]
                csrf = json.loads(response.read())["csrf_token"]
            status, started = call(base, cookie, csrf, "POST", "/new", {})
            assert status == 201, started
            draft, revision = started["draft_id"], started["revision"]
            for step, data in STEPS.items():
                status, saved = call(base, cookie, csrf, "POST", f"/new/{draft}/steps/{step}",
                                     {"base_revision": revision, "data": data})
                assert status == 200, saved
                revision = saved["revision"]
                print(f"step {step} saved, figures: {saved['figures']}")
            status, preview = call(base, cookie, csrf, "GET", f"/new/{draft}/preview")
            assert status == 200, preview
            status, made = call(base, cookie, csrf, "POST", f"/new/{draft}/create",
                               {"confirm": True, "protocol_sha256": preview["protocol_sha256"]})
            assert status == 201, made
            project = load_project(root / "projects" / made["project"])
            digest = flows.protocol_digest(project)
            assert digest == preview["protocol_sha256"] == made["protocol_sha256"], "digest mismatch"
            print(f"created {made['project']}: registry v{project.registry_version} ({project.frozen_at}), "
                  f"floor v{project.floor_version}, {len(project.questions)} questions, digest {digest[:12]}")
            print("OK: the project loads with the real loader and carries the previewed protocol")
            return 0
        finally:
            httpd.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
