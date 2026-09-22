"""Command line entry point.

Only `validate` exists so far: it enforces the input contract. Stages 1-6 described in
README.md are not implemented yet, and the CLI says so rather than pretending.
"""

from __future__ import annotations

import argparse
import sys

from claimstone import __version__
from claimstone.config import ConfigError, discover_projects, load_project

STAGES = ("discover", "acquire", "normalize", "extract", "review", "synthesize")


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
            f"OK   {project.name}: "
            f"{len(project.topics)} topics, "
            f"{len(project.questions)} questions "
            f"(registry v{project.registry_version}, frozen {project.frozen_at}), "
            f"{len(project.classes)} source classes, "
            f"acquisition floor {project.acquisition_floor:.2f}"
        )
    return 1 if failures else 0


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

    for stage in STAGES:
        placeholder = sub.add_parser(stage, help=f"(not implemented) stage: {stage}")
        placeholder.set_defaults(func=_not_implemented, stage_name=stage)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
