"""Command line entry point.

Stages that exist have commands; the four that do not say so rather than pretending.
"""

from __future__ import annotations

import argparse
import sys

from claimstone import __version__
from typing import TYPE_CHECKING

from claimstone.config import ConfigError, discover_projects, load_project

if TYPE_CHECKING:  # import cost at startup matters for a CLI; these are annotations only
    from claimstone.config import Project
    from claimstone.store import Store

STAGES = ("normalize", "extract", "review", "synthesize")

SWEEP_VALUES = {
    "min_text_chars": [1000, 2000, 3000, 4000, 5000, 8000],
    "min_pdf_bytes": [2000, 5000, 10000, 20000, 50000],
    "paywall_doubt_chars": [6000, 9000, 12000, 16000, 24000],
    "fulltext_chars": [8000, 12000, 15000, 20000, 30000],
}


def _validate(args: argparse.Namespace) -> int:
    roots = discover_projects(args.projects_dir) if args.all_projects else [args.project]
    if not roots:
        print(f"no project found under {args.projects_dir}/", file=sys.stderr)
        return 1

    failures = 0
    for root in roots:
        try:
            project = load_project(root)
        except ConfigError as exc:
            print(f"FAIL {root}: {exc}", file=sys.stderr)
            failures += 1
            continue
        manifest = f", {len(project.manifest)} manifest rows" if project.manifest else ""
        print(
            f"OK   {project.name}: "
            f"{len(project.topics)} topics, "
            f"{len(project.questions)} questions "
            f"(registry v{project.registry_version}, frozen {project.frozen_at}), "
            f"{len(project.classes)} source classes, "
            f"acquisition floor {project.acquisition_floor:.2f} "
            f"(v{project.floor_version}){manifest}, "
            f"registry {project.registry_sha256[:12]}"
        )
    return 1 if failures else 0


def _import_manifest(args: argparse.Namespace) -> int:
    from claimstone import discover
    from claimstone.store import Store

    project = load_project(args.project)
    if not project.manifest:
        print(f"no manifest.tsv under {args.project}/", file=sys.stderr)
        return 1
    result = discover.import_manifest(_checked_store(args, project), project.manifest)
    print(f"{project.name}: {result['new']} new, {result['updated']} corrected, "
          f"of {result['rows']} manifest rows")
    return 0


def _checked_store(args: argparse.Namespace, project: "Project") -> "Store":
    """The project's store, with the question registry verified against what it last saw.

    Run wherever a store is opened rather than in one command: a drift check that only fires when
    someone remembers to ask for it protects nothing.
    """
    from claimstone.config import check_registry_drift
    from claimstone.store import Store

    store = Store(project.name, base=args.store)
    check_registry_drift(project, store)
    return store


def _acquire(args: argparse.Namespace) -> int:
    from claimstone import acquire, net, resolve

    retry_classes = frozenset(args.retry_class or ())
    if retry_classes and not args.campaign:
        print(
            "refusing to re-request a terminal failure on an unnamed run: pass --campaign NAME "
            "so the ledger records why this round knocked again",
            file=sys.stderr,
        )
        return 2

    project = load_project(args.project)
    store = _checked_store(args, project)
    fetcher = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
    candidates = list(store.latest_by("candidates.jsonl", "candidate_key").values())

    if args.dry_run:
        for candidate in candidates:
            locations, _ = resolve.plan(fetcher, candidate, use_apis=not args.no_apis)
            print(f"{candidate.get('source_id') or candidate['candidate_key']}")
            for position, location in enumerate(locations, start=1):
                print(f"  {position}. {location.provenance:<10} {location.url}")
        return 0

    done = 0
    obtained = 0
    total = len(candidates)
    for row in acquire.run(
        candidates, store, fetcher,
        campaign=args.campaign or acquire.ROUTINE,
        retry_classes=retry_classes,
        use_apis=not args.no_apis,
        thresholds=project.gate_thresholds,
        policy=project.gate_policy,
        limit=args.limit,
    ):
        done += 1
        if row["acquired"]:
            obtained += 1
            detail = f"{row.get('provenance')}  {row.get('licence') or 'licence unrecorded'}"
            size = f"{(row.get('bytes') or 0) // 1024} KB"
        else:
            detail = str(row.get("failure_class"))
            size = ""
        # Progress on stderr, summary on stdout: `acquire … > summary.txt` keeps both, and a
        # round that takes minutes cannot be mistaken for a hung one.
        print(
            f"[{done:>3}/{total}] {obtained / done:.2f}  "
            f"{'ok  ' if row['acquired'] else 'fail'}  "
            f"{row.get('source_id') or row['candidate_key']}  {detail}  {size}".rstrip(),
            file=sys.stderr,
        )
    print(f"{done} attempted, {obtained} obtained")
    return 0


def _report(args: argparse.Namespace) -> int:
    from claimstone import admissibility
    from claimstone.store import Store

    project = load_project(args.project)
    result = admissibility.admit(project, _checked_store(args, project))

    if args.json:
        import json

        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{project.name} — round {result['round'] or 'all'}")
        # Per class before pooled: D3 says classes are not mixed, and an aggregate that hides
        # one class sitting at zero is a different fact from a uniform one.
        for klass, bucket in result["by_class"].items():
            print(f"  {klass:<14} {bucket['obtained']}/{bucket['found']}  {bucket['rate']:.2f}")

        # The chain of states, separately, because the remedies differ: a rule to declare, a
        # round to finish, a campaign to run, a stage 3 to run.
        found = result["found"]
        print(f"  {'found':<14} {found}")
        if result["unclassified"]:
            print(f"  {'classified':<14} {result['classified']}/{found}"
                  f"   {result['unclassified']} unclassified, which acquire will refuse")
        print(f"  {'attempted':<14} {result['attempted']}/{found}")
        share = "—" if not found else f"{result['obtained'] / found:.2f}"
        print(f"  {'obtained':<14} {result['obtained']}/{found}  {share}")
        if result["confirmed"] is not None:
            marker = "  <- the figure" if result["basis"] == "confirmed" else ""
            print(f"  {'confirmed':<14} {result['confirmed']}/{found}"
                  f"  {result['confirmed'] / found:.2f}{marker}")
            if result["not_a_document"]:
                print(f"                 {len(result['not_a_document'])} obtained but not a "
                      f"document: {', '.join(result['not_a_document'])}")
            if result["awaiting_normalize"]:
                print(f"                 {result['awaiting_normalize']} still awaiting "
                      f"normalize, so the figure stays the obtained rate")
        if result["orphan_acquisitions"]:
            print(f"  {'orphans':<14} {len(result['orphan_acquisitions'])} acquisition rows with "
                  f"no candidate — the ledger is inconsistent")
        print(f"  {'floor':<14} {result['floor']:.2f}"
              f" (v{result['floor_version']}, {result['floor_set_at']})"
              f"   {result['status']}   basis: {result['basis']}")
        for name, counts in (("failures", result["failures_by_class"]),
                             ("by host", result["failures_by_host"])):
            if counts:
                print(f"  {name:<14} " + "  ".join(f"{k} {v}" for k, v in counts.items()))

    return 3 if args.gate and result["status"] == admissibility.INSUFFICIENT else 0


def _gate_audit(args: argparse.Namespace) -> int:
    from claimstone import gate_audit
    from claimstone.store import Store

    project = load_project(args.project)
    store = _checked_store(args, project)

    name = args.sweep or "min_text_chars"
    points = gate_audit.sweep(store, name, SWEEP_VALUES[name])
    listing = gate_audit.rejections(store, project.gate_thresholds, project.gate_policy)

    if args.json:
        import json

        print(json.dumps({"sweep": {name: points}, "rejections": listing}, indent=2))
        return 0

    print(f"{name:<20}" + "".join(f"{p['value']:>8}" for p in points))
    print(f"{'rate':<20}" + "".join(
        f"{'—':>8}" if p["rate"] is None else f"{p['rate']:>8.2f}" for p in points))
    spread = [p["rate"] for p in points if p["rate"] is not None]
    if spread and max(spread) - min(spread) > 0.05:
        print(f"\n  this threshold is deciding the rate (spread "
              f"{max(spread) - min(spread):.2f}) — read the boundary cases by hand")
    elif spread:
        print(f"\n  flat across the range (spread {max(spread) - min(spread):.2f}): "
              f"the chosen value is not load-bearing")

    if args.show_rejected:
        print(f"\n{len(listing)} rejected:")
        for item in listing:
            chars = "—" if item["chars"] is None else str(item["chars"])
            print(f"  {item['source_id'] or '?':<8} {item['kind']:<18} {chars:>7} chars"
                  f"  {item['reason']}")
            print(f"           {item['stored_path']}")
    return 0


def _regate(args: argparse.Namespace) -> int:
    from claimstone import fulltext, gate_audit
    from claimstone.store import Store

    project = load_project(args.project)
    store = _checked_store(args, project)

    changed = 0
    total = 0
    for row in gate_audit.regate(store, campaign=args.campaign,
                                 thresholds=project.gate_thresholds,
                                 policy=project.gate_policy):
        total += 1
        verdict = row["gate"]["kind"]
        mark = "ok  " if row["acquired"] else "fail"
        if not row["acquired"]:
            changed += 1
        print(f"{mark}  {row.get('source_id') or row['candidate_key']:<8} {verdict}",
              file=sys.stderr)
    print(f"{total} re-judged under gate_version {fulltext.GATE_VERSION}, "
          f"{total - changed} still full text")
    return 0


def _not_implemented(args: argparse.Namespace) -> int:
    print(
        f"stage '{args.stage_name}' is not implemented yet — see README.md, 'The six stages'",
        file=sys.stderr,
    )
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claimstone", description="Topics in, verdicts out.")
    parser.add_argument("--version", action="version", version=f"claimstone {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="check a project's input contract")
    group = validate.add_mutually_exclusive_group(required=True)
    group.add_argument("project", nargs="?", help="path to a project directory")
    group.add_argument("--all-projects", action="store_true", help="validate every project")
    validate.add_argument("--projects-dir", default="projects")
    validate.set_defaults(func=_validate)

    for name, handler, help_text in (
        ("import-manifest", _import_manifest, "seed candidates from manifest.tsv"),
        ("acquire", _acquire, "stage 2: obtain the full texts"),
        ("report", _report, "acquisition rate, per class, against the floor"),
        ("gate-audit", _gate_audit, "how much the rate depends on the gate thresholds"),
        ("regate", _regate, "re-judge bytes already held under the current gate; no network"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("project", help="path to a project directory")
        command.add_argument("--store", default="store", help="where generated data lives")
        command.set_defaults(func=handler)
        if name == "acquire":
            command.add_argument("--campaign", help="name this run; required with --retry-class")
            command.add_argument("--retry-class", action="append",
                                 help="re-request a terminal failure class, e.g. PAYWALL_403")
            command.add_argument("--limit", type=int, default=None)
            command.add_argument("--no-apis", action="store_true",
                                 help="plan from the candidate URL alone; no Unpaywall or OpenAlex")
            command.add_argument("--dry-run", action="store_true",
                                 help="print the planned cascade and fetch nothing")
        if name == "report":
            command.add_argument("--json", action="store_true")
            command.add_argument("--gate", action="store_true",
                                 help="exit 3 when the round is INSUFFICIENT_ACQUISITION")
        if name == "regate":
            command.add_argument("--campaign", required=True,
                                 help="name this re-reading; it lands on every corrected row")
        if name == "gate-audit":
            command.add_argument("--sweep", choices=sorted(SWEEP_VALUES),
                                 help="which threshold to sweep (default min_text_chars)")
            command.add_argument("--show-rejected", action="store_true",
                                 help="list every rejected artifact for a by-hand check")
            command.add_argument("--json", action="store_true")

    for stage in STAGES:
        placeholder = sub.add_parser(stage, help=f"(not implemented) stage: {stage}")
        placeholder.set_defaults(func=_not_implemented, stage_name=stage)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ConfigError as exc:
        # A contract violation is the user's to fix, so it gets a sentence rather than a
        # traceback. `validate` handles its own and never reaches here.
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
