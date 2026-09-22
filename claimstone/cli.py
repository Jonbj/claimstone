"""Command line entry point.

Stages that are not implemented say so and exit non-zero rather than pretending.
"""

from __future__ import annotations

import argparse
import json
import sys

from claimstone import __version__, acquire, discover, net
from claimstone.config import ConfigError, discover_projects, load_project

STAGES = ("normalize", "extract", "review", "synthesize")


def _load(args: argparse.Namespace):
    project = load_project(args.project)
    from claimstone.store import Store

    return project, Store(project.name, args.store_dir)


def _fetcher(project, args: argparse.Namespace) -> net.Fetcher:
    return net.Fetcher(
        excluded_hosts=frozenset(h.lower() for h in project.excluded_hosts),
        obey_robots=not args.ignore_robots,
        timeout_s=args.timeout,
    )


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
        print(
            f"OK   {project.name}: {len(project.topics)} topics, "
            f"{len(project.questions)} questions "
            f"(registry v{project.registry_version}, frozen {project.frozen_at}), "
            f"{len(project.classes)} source classes, "
            f"acquisition floor {project.acquisition_floor:.2f}"
        )
    return 1 if failures else 0


def _discover(args: argparse.Namespace) -> int:
    project, store = _load(args)
    summary = discover.run(
        project,
        store,
        _fetcher(project, args),
        apis=args.api or tuple(discover.SEARCHERS),
        topics=args.topic or None,
        per_query=args.per_query,
    )
    print(
        f"discover: {summary['returned']} returned, {summary['new']} new, "
        f"{summary['total']} candidates total"
    )
    return 0


def _import_manifest(args: argparse.Namespace) -> int:
    project, store = _load(args)
    summary = discover.import_manifest(store, args.tsv)
    print(f"import: {summary['rows']} rows read, {summary['new']} new, {summary['total']} total")
    return 0


def _acquire(args: argparse.Namespace) -> int:
    project, store = _load(args)
    candidates = list(store.latest_by("candidates.jsonl", "candidate_key").values())
    if args.limit:
        candidates = candidates[: args.limit]
    if not candidates:
        print("no candidates: run discover or import-manifest first", file=sys.stderr)
        return 1

    fetcher = _fetcher(project, args)
    for row in acquire.run(
        candidates, store, fetcher, skip_acquired=not args.refetch, use_apis=not args.no_apis
    ):
        mark = "ok  " if row["acquired"] else "FAIL"
        label = row.get("source_id") or row["candidate_key"][:44]
        detail = row.get("provenance") if row["acquired"] else row.get("failure_class")
        print(f"{mark} {label:<46} {detail}")
    return _status(args)


def _status(args: argparse.Namespace) -> int:
    project, store = _load(args)
    stats = acquire.rate(store)
    floor = project.acquisition_floor
    admissible = stats["attempted"] > 0 and stats["rate"] >= floor

    if getattr(args, "json", False):
        print(json.dumps({**stats, "floor": floor, "admissible": admissible}, indent=2))
        return 0

    print(f"\nproject: {project.name}")
    print(f"attempted: {stats['attempted']}   acquired: {stats['acquired']}")
    print(f"rate:      {stats['rate']:.2f}   floor: {floor:.2f}")
    print(
        "verdicts:  ADMISSIBLE"
        if admissible
        else "verdicts:  INSUFFICIENT_ACQUISITION — this round may not produce verdicts"
    )
    if stats["failures_by_class"]:
        print("\nfailures by class:")
        for name, count in stats["failures_by_class"].items():
            print(f"  {count:4d}  {name}")
    if stats["failures_by_host"]:
        print("\nfailures by host:")
        for host, count in list(stats["failures_by_host"].items())[:12]:
            print(f"  {count:4d}  {host}")
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

    def with_project(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("project", help="path to a project directory")
        p.add_argument("--store-dir", default="store")
        p.add_argument("--timeout", type=int, default=30)
        p.add_argument(
            "--ignore-robots",
            action="store_true",
            help="not for routine use; the default respects robots.txt",
        )
        return p

    validate = sub.add_parser("validate", help="check a project's input contract")
    group = validate.add_mutually_exclusive_group(required=True)
    group.add_argument("project", nargs="?", help="path to a project directory")
    group.add_argument("--all-projects", action="store_true")
    validate.add_argument("--projects-dir", default="projects")
    validate.set_defaults(func=_validate)

    disc = with_project(sub.add_parser("discover", help="stage 1: topics to candidates"))
    disc.add_argument("--api", action="append", choices=list(discover.SEARCHERS), default=None)
    disc.add_argument("--topic", action="append", default=None, help="restrict to a topic id")
    disc.add_argument("--per-query", type=int, default=25)
    disc.set_defaults(func=_discover)

    imp = with_project(sub.add_parser("import-manifest", help="seed candidates from a TSV"))
    imp.add_argument("--tsv", required=True)
    imp.set_defaults(func=_import_manifest)

    acq = with_project(sub.add_parser("acquire", help="stage 2: candidates to frozen texts"))
    acq.add_argument("--limit", type=int, default=0)
    acq.add_argument("--refetch", action="store_true", help="retry candidates already held")
    acq.add_argument("--no-apis", action="store_true", help="skip OA resolution (offline test)")
    acq.set_defaults(func=_acquire)

    stat = with_project(sub.add_parser("status", help="acquisition accounting and admissibility"))
    stat.add_argument("--json", action="store_true")
    stat.set_defaults(func=_status)

    for stage in STAGES:
        placeholder = with_project(sub.add_parser(stage, help=f"(not implemented) stage: {stage}"))
        placeholder.set_defaults(func=_not_implemented, stage_name=stage)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    except net.ContactNotConfigured as exc:
        print(f"{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
