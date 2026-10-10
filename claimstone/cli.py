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

# Every stage is implemented. The tuple stays because the placeholder mechanism is how an
# unimplemented stage says so rather than pretending, and the next stage added will want it.
STAGES: tuple[str, ...] = ()

# Named here rather than imported, because building the parser must not pull in three runner
# modules. `test_cli_model.py` pins this list against `runners.available()`.
BACKENDS = ("claude-cli", "codex-cli", "llamacpp", "ollama-cloud", "opencode-cli")

# Same reason: the parser must not import stage 6 to render its help. `test_synthesize.py` pins this
# against `synthesize.VERDICTS`, so a state added there cannot go unofferable here.
VERDICT_NAMES = ("SUPPORTED", "CONTRADICTED", "CONTESTED_IN_LITERATURE",
                 "UNANSWERED_IN_LITERATURE", "NEVER_ASKED")

# The boundaries the corpus actually separates at are 1 vs 2 references and 4,377 vs 4,378
# characters, so both ranges reach below the default: an audit whose lowest value already confirms
# everything reports "flat" without ever finding the edge. See D21.
CONFIRM_SWEEP_VALUES = {
    "min_references": [1, 2, 3, 5, 8, 12, 20],
    "confirm_chars": [2000, 5000, 10000, 15000, 25000, 40000],
}

SWEEP_VALUES = {
    "min_text_chars": [1000, 2000, 3000, 4000, 5000, 8000],
    "min_pdf_bytes": [2000, 5000, 10000, 20000, 50000],
    "paywall_doubt_chars": [6000, 9000, 12000, 16000, 24000],
    "fulltext_chars": [8000, 12000, 15000, 20000, 30000],
}


def extract_kinds() -> tuple[str, ...]:
    """Named for the parser's help without importing the stage at startup."""
    from claimstone.claimgate import STANCES_BY_KIND

    return tuple(STANCES_BY_KIND)


def grobid_url_default() -> str:
    import os

    from claimstone.grobid import DEFAULT_URL

    return os.environ.get("CLAIMSTONE_GROBID_URL") or DEFAULT_URL


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

    project = load_project(args.project)
    if not project.manifest:
        print(f"no manifest.tsv under {args.project}/", file=sys.stderr)
        return 1
    result = discover.import_manifest(_checked_store(args, project), project.manifest,
                                      round_name=args.round, population_policy=project.population)
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
    from claimstone import acquire, net, resolve, population

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
    for round_name in {str(c.get("round") or "routine") for c in candidates
                       if args.round is None or c.get("round") == args.round}:
        population.check_round(store, project.population, round_name, record=False)

    if args.dry_run:
        previous = store.latest_by('acquisitions.jsonl', 'candidate_key')
        for candidate in acquire.eligible_candidates(candidates, previous,
                retry_classes=retry_classes, round_name=args.round, manifest_only=args.manifest,
                only_oa=args.only_oa, limit=args.limit):
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
        round_name=args.round,
        manifest_only=args.manifest,
        only_oa=args.only_oa,
        classes=project.classes,
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

    project = load_project(args.project)
    # A round is the unit the floor is judged on. Without this, a discovery sweep's candidates join a
    # settled manifest round in one denominator and the figure compares two populations: measured on
    # the real store, one citation sweep took 14/25 = 0.56 to 14/75 = 0.19, which is true of the store
    # and means nothing as a comparison.
    result = admissibility.admit(project, _checked_store(args, project), round_name=args.round,
                                 manifest_only=args.manifest)

    if args.json:
        import json

        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{project.name} — round {result['round'] or 'all'}")
        # Per class before pooled: D3 says classes are not mixed, and an aggregate that hides
        # one class sitting at zero is a different fact from a uniform one.
        for klass, bucket in result["by_class"].items():
            # Each class against its own bar when it declares one, the project's otherwise. A declared class
            # floor is an additional constraint and never a shortcut: the project floor still judges the whole.
            own = " (declared)" if klass in result["class_floors"] else ""
            mark = "" if bucket["meets_floor"] else "  <- below its floor"
            print(f"  {klass:<14} {bucket[bucket['basis']]}/{bucket['found']} {bucket['basis']}  {bucket['rate']:.2f}"
                  f"   floor {bucket['floor']:.2f}{own}{mark}")

        # The chain of states, separately, because the remedies differ: a rule to declare, a
        # round to finish, a campaign to run, a stage 3 to run.
        found = result["found"]
        print(f"  {'found':<14} {found}")
        if result.get('discovery_failures'):
            print(f"  incomplete search: {result['discovery_failures']}/{result['discovery_queries']} failed")
        if result["unclassified"]:
            print(f"  {'classified':<14} {result['classified']}/{found}"
                  f"   {result['unclassified']} unclassified, which acquire will refuse")
        print(f"  {'attempted':<14} {result['attempted']}/{found}")
        share = "—" if not found else f"{result['obtained'] / found:.2f}"
        print(f"  {'obtained':<14} {result['obtained']}/{found}  {share}")
        if not found and args.round:
            # A named round matching nothing is a real answer, and a different one from a round that
            # found nothing obtainable. Only when a round was named: without one, no candidates at all
            # while acquisitions exist is a broken ledger, and it must still reach the gate below.
            print(f"  no candidate carries round {args.round!r}")
            return 0
        if result["basis"] == "confirmed":
            print(f"  {'confirmed':<14} {result['confirmed']}/{found}"
                  f"  {result['rate']:.2f}  <- the figure")
            if result["rate_upper"] != result["rate"]:
                print(f"                 could still reach {result['rate_upper']:.2f} once "
                      f"{result['awaiting_normalize']} awaiting normalize are examined")
            if result["not_a_document"]:
                print(f"                 {len(result['not_a_document'])} obtained but not a "
                      f"document: {', '.join(result['not_a_document'])}")
        if result["orphan_acquisitions"]:
            print(f"  {'orphans':<14} {len(result['orphan_acquisitions'])} acquisition rows with "
                  f"no candidate — the ledger is inconsistent")
        print(f"  {'floor':<14} {result['floor']:.2f}"
              f" (v{result['floor_version']}, {result['floor_set_at']})"
              f"   {result['status']}   basis: {result['basis']}")
        if not result["final"]:
            # Only a final round may produce verdicts. Saying which conditions are outstanding is
            # the difference between a provisional figure and one mistaken for settled.
            print(f"  {'provisional':<14} not final: {', '.join(result['blocking'])}")
        for name, counts in (("failures", result["failures_by_class"]),
                             ("by host", result["failures_by_host"])):
            if counts:
                print(f"  {name:<14} " + "  ".join(f"{k} {v}" for k, v in counts.items()))

    return 3 if args.gate and result["status"] == admissibility.INSUFFICIENT else 0


def _gate_audit(args: argparse.Namespace) -> int:
    from claimstone import gate_audit

    project = load_project(args.project)
    store = _checked_store(args, project)

    name = args.sweep or "min_text_chars"
    points = gate_audit.sweep(store, name, SWEEP_VALUES[name], thresholds=project.gate_thresholds,
                              policy=project.gate_policy, classes=project.classes,
                              round_name=args.round, manifest_only=args.manifest)
    listing = gate_audit.rejections(store, project.gate_thresholds, project.gate_policy,
                                   classes=project.classes, round_name=args.round,
                                   manifest_only=args.manifest)

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

    project = load_project(args.project)
    store = _checked_store(args, project)

    changed = 0
    total = 0
    for row in gate_audit.regate(store, campaign=args.campaign,
                                 thresholds=project.gate_thresholds,
                                 policy=project.gate_policy, classes=project.classes):
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


def _normalize(args: argparse.Namespace) -> int:
    from claimstone import grobid as grobid_mod
    from claimstone import normalize

    project = load_project(args.project)
    store = _checked_store(args, project)

    if args.confirm_audit:
        # No GROBID and no network: what was parsed is on disk under its hash.
        name = args.sweep or "min_references"
        points = normalize.confirm_sweep(store, name, CONFIRM_SWEEP_VALUES[name])
        if not points or not points[0]["documents"]:
            print(f"{project.name}: no documents normalized yet")
            return 0
        print(f"{name:<18}" + "".join(f"{p['value']:>8}" for p in points))
        print(f"{'confirmed':<18}" + "".join(f"{p['confirmed']:>8}" for p in points))
        counts = [p["confirmed"] for p in points]
        total = points[0]["documents"]
        if max(counts) - min(counts) > 1:
            print(f"\n  this threshold is deciding confirmation (spread "
                  f"{max(counts) - min(counts)} of {total}) — read the boundary cases by hand")
        else:
            print(f"\n  flat across the range: the chosen value is not load-bearing "
                  f"({total} documents)")
        if points[0]["unreadable"]:
            print(f"  {points[0]['unreadable']} document(s) could not be re-read and are excluded")
        return 0

    # The container is not checked up front. `full_text` refuses when GROBID is not answering, and
    # a source whose TEI is already on disk never reaches it — the whole corpus can be re-chunked
    # with nothing running, which is the point of storing the TEI under its hash. Demanding a
    # container that will never be contacted is a wall in front of an offline operation.
    client = grobid_mod.Grobid(url=args.grobid_url)
    done = confirmed = unreadable = 0
    rows = normalize.run(store, client, thresholds=project.normalize_thresholds,
                         force=args.force, limit=args.limit)
    while True:
        try:
            row = next(rows)
        except StopIteration:
            break
        except grobid_mod.GrobidUnavailable as exc:
            # Whatever was normalized before this point is already in the ledger: append-only and
            # idempotent by hash, so the run resumes here once the container is up.
            print(str(exc), file=sys.stderr)
            if done:
                print(f"{done} normalized before GROBID was needed, {confirmed} confirmed",
                      file=sys.stderr)
            return 2
        done += 1
        verdict = row["fulltext_confirmed"]
        if verdict:
            confirmed += 1
            mark = "ok  "
            detail = (f"{row['chunks']} chunks, {row['references']} refs, "
                      f"{row['tables']} tables, {row['body_chars']} chars")
        elif verdict is None:
            # Nothing was established, so it is neither. Printing it as a failure would read as a
            # source the rule rejected, and the two are not the same fact.
            unreadable += 1
            mark = "??  "
            detail = f"{row.get('failure_class')}  {str(row.get('reason', ''))[:60]}"
        else:
            mark = "fail"
            detail = f"{row.get('failure_class')}  {str(row.get('reason', ''))[:60]}"
        print(f"[{done:>3}] {mark}  {row['source_id']:<8} {detail}", file=sys.stderr)

    summary = f"{done} normalized, {confirmed} confirmed as documents"
    if unreadable:
        summary += (f", {unreadable} unreadable — these stay awaiting, so the round cannot "
                    f"certify itself until the bytes are back")
    print(summary)
    return 0


APIS = ("openalex", "crossref", "arxiv")


def _discover(args: argparse.Namespace) -> int:
    from claimstone import discover

    unknown = [api for api in (args.api or ()) if api not in APIS]
    if unknown:
        print(f"unknown api: {', '.join(unknown)} (known: {', '.join(APIS)})", file=sys.stderr)
        return 2

    project = load_project(args.project)
    store = _checked_store(args, project)

    if args.promote_contested:
        # Reads two ledgers, opens no socket. D26: a rejected SECONDHAND_CLAIM names a work the corpus
        # relies on, and a work cited once for a contradiction is worth more than a textbook cited
        # three times.
        result = discover.promote_contested(project, store, round_name=args.round)
        print(f"{result['named']} work(s) named in rejected secondhand claims, "
              f"{result['promoted']} promoted past the citation threshold")
        for surname, year in result["unmatched"]:
            print(f"  {surname} ({year}) is named and is not in the bibliography — "
                  f"nothing here knows its title or address, so nothing was invented")
        for surname, year, count in result["ambiguous"]:
            print(f"  {surname} ({year}): {count} reference(s) by that name and none with that year. "
                  f"Promoting on the surname alone would admit all {count}; read them by hand")
        return 0

    if args.reclassify:
        # No socket: the rules are in sources.yaml and the candidates are on disk, so re-applying one
        # to the other costs nothing. The counterpart of `regate` and `model-run --rejudge`.
        result = discover.reclassify(project, store)
        print(f"{result['changed']} candidate(s) reclassified, "
              f"{result['declared']} left alone because the manifest declared their class")
        for move, count in result["moves"].items():
            print(f"  {move}  {count}")
        if result["unclassified"]:
            print(f"  {result['unclassified']} still unclassified: {result['uncovered']}")
        return 0

    topics = tuple(t.strip() for t in args.topics.split(",")) if args.topics else None
    incomplete = False

    # Keyword first, then citations, and the order matters for more than tidiness. Both channels
    # skip a candidate_key already present, so whichever runs first owns a work both found. A
    # keyword row carries its topic and query; a citation row does not. And the overlap in
    # discover-report is computed as keyword keys against reference keys, so letting citations
    # claim a shared work first would make that number undercount the very thing it measures.
    if args.channel in ("keyword", "both"):
        from claimstone import net

        fetcher = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))
        result = discover.run(project, store, fetcher,
                              apis=tuple(args.api) if args.api else APIS,
                              topics=topics, per_query=args.per_query, round_name=args.round)
        print(f"keyword channel: {result['new']} new of {result['returned']} returned, "
              f"{result['queries']} queries")
        if result.get("failures"):
            incomplete = True
            print(f"  incomplete search: {result['completed_queries']}/{result['queries']} completed; {result['failures']}")
        if result["unclassified"]:
            print(f"  {result['unclassified']} unclassified: {result['uncovered']}")
            print("  declare an assign_when rule in sources.yaml rather than loosening one")

    if args.channel in ("citation", "both"):
        # A fetcher only when asked for. Without --resolve this channel reads a ledger and opens no
        # socket, which is the promise that lets it re-run for free — so resolution is opt-in rather
        # than something the channel does because it can.
        resolver = None
        if args.resolve:
            from claimstone import net

            try:
                net.contact_email()
            except net.ContactNotConfigured as exc:
                print(str(exc), file=sys.stderr)
                return 2
            resolver = net.Fetcher(excluded_hosts=frozenset(project.excluded_hosts))

        result = discover.run_citations(project, store, round_name=args.round, fetcher=resolver)
        if not result["references_available"]:
            print("citation channel: nothing to read — no references.jsonl yet "
                  "(run `claimstone normalize` first)")
        else:
            print(f"citation channel: {result['new']} new of {result['admitted']} admitted, "
                  f"from {result['considered']} references")
            if result["resolved"]:
                print(f"  {result['resolved']} resolved to a venue and an address")
            if result["unresolved"]:
                print("  unresolved: " + "  ".join(
                    f"{k} {v}" for k, v in result["unresolved"].items()))
                if "NOT_ATTEMPTED" in result["unresolved"]:
                    print("  pass --resolve to look these up; without a venue or an address "
                          "stage 2 refuses them, correctly")
            if result["possible_duplicates"]:
                print(f"  {result['possible_duplicates']} noted as possible duplicates, "
                      f"none merged")
    return 3 if incomplete else 0


def _discover_report(args: argparse.Namespace) -> int:
    from claimstone import discover_report

    project = load_project(args.project)
    summary = discover_report.summarise(
        _checked_store(args, project), round_name=args.round)

    if args.json:
        import json

        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    if summary['search']['recorded_queries']:
        search = summary['search']
        print(f"  search completion {search['completed']}/{search['recorded_queries']}; {search['failed']} failed")
    if not summary["candidates"]:
        print(f"{project.name}: no candidates recorded")
        return 0

    print(f"{project.name} — round {summary['round'] or 'all'}")
    keyword, citation = summary["keyword"], summary["citation"]
    print(f"  keyword channel   {keyword['candidates']:>5} candidates   "
          f"{keyword['topics']} topics, {keyword['queries']} queries")
    print(f"  citation channel  {citation['candidates']:>5} candidates   "
          f"of {citation['references_seen']} references")
    print(f"  overlap           {summary['overlap']:>5} works found by both channels")
    if summary["unclassified"]:
        print(f"  unclassified      {summary['unclassified']:>5}   {summary['uncovered']}")
    for name in ("keyword", "citation"):
        by_class = summary[name]["by_class"]
        if by_class:
            print(f"  {name:<17} " + "  ".join(f"{k} {v}" for k, v in by_class.items()))
    print(f"\n  {summary['caveat']}")
    return 0


def _model_run(args: argparse.Namespace) -> int:
    from claimstone import model_call, runners

    if args.lane not in model_call.LANES:
        print(f"unknown lane {args.lane!r}: {', '.join(model_call.LANES)}", file=sys.stderr)
        return 2
    extra: dict[str, object] = {} if args.think is None else {"think": args.think}
    if args.enforce_schema:
        extra["enforce_schema"] = True
    try:
        runner = runners.build(args.backend, model=args.model, **extra)
    except ValueError as exc:
        # Includes "this backend needs --model": a missing model is a usage error with a sentence,
        # not a TypeError from a constructor.
        print(str(exc), file=sys.stderr)
        return 2

    project = load_project(args.project)
    store = _checked_store(args, project)
    queue = model_call.Queue(store, lane=args.lane, batch=args.batch)

    if args.rejudge:
        # No backend is contacted: the answers are on disk under their hashes, so asking what the
        # current rules make of them costs nothing. The counterpart of `regate`.
        done = ok = 0
        for row in model_call.rejudge(queue, backend=runner.name):
            done += 1
            ok += bool(row["ok"])
            mark = "ok  " if row["ok"] else "fail"
            print(f"[{done:>4}] {mark}  {row['call_id'][:12]}"
                  f"  {row.get('failure_class') or ''}", file=sys.stderr)
        print(f"{done} re-read, {ok} now valid — no call was made and nothing was paid")
        return 0

    # Per backend, like everything else about the queue: how much is left to do depends on who is
    # doing it, which is the whole point of two backends draining one requests file.
    retry = frozenset(args.retry_class or ())
    unknown = sorted(retry - set(model_call.TERMINAL) - set(model_call.TRANSIENT))
    if unknown:
        print(f"unknown failure class: {', '.join(unknown)}", file=sys.stderr)
        return 2
    pending = len(queue.pending(backend=runner.name,
                               model=str(getattr(runner, "model", "") or ""),
                               retry_classes=retry))
    done = ok = 0
    for row in model_call.drain(queue, runner, limit=args.limit, retry_classes=retry):
        done += 1
        if row["ok"]:
            ok += 1
        mark = "ok  " if row["ok"] else "fail"
        detail = "" if row["ok"] else f"  {row['failure_class']}"
        print(f"[{done:>4}/{pending}] {ok / done:.2f}  {mark}  {row['call_id'][:12]}"
              f"  {row['latency_s']:.1f}s{detail}", file=sys.stderr)
    print(f"{done} answered, {ok} valid, on {runner.name} ({runner.harness_version()})")
    return 0


def _model_report(args: argparse.Namespace) -> int:
    from claimstone import model_report

    project = load_project(args.project)
    summary = model_report.summarise(
        _checked_store(args, project), lane=args.lane, batch=args.batch)

    if args.json:
        import json

        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    if not summary["calls"]:
        print(f"{project.name} {args.lane}/{args.batch}: no calls recorded")
        return 0

    print(f"{project.name} {args.lane}/{args.batch} — {summary['calls']} calls, "
          f"{summary['ok']} valid")
    for backend, bucket in summary["by_reader"].items():
        cost = "unpriced" if bucket["cost_usd"] is None else f"${bucket['cost_usd']:.4f}"
        if bucket["unpriced"] and bucket["cost_usd"] is not None:
            cost += f" (+{bucket['unpriced']} unpriced)"
        rate = "—" if bucket["attempts_per_hour"] is None else f"{bucket['attempts_per_hour']:.0f}/h"
        print(f"  {backend:<34} {bucket['ok']}/{bucket['calls']}  {cost:<20} {rate:>9}")
        if bucket["attempt_failures_by_class"]:
            print("                 " + "  ".join(
                f"{k} {v}" for k, v in bucket["attempt_failures_by_class"].items()))
    return 0


def _extract(args: argparse.Namespace) -> int:
    from claimstone import extract

    project = load_project(args.project)
    store = _checked_store(args, project)

    if args.harvest:
        # No socket: the answers are on disk, so re-running after a gate change costs nothing — the
        # arrangement gate-audit, normalize --confirm-audit and model-run --rejudge already use.
        result = extract.harvest(project, store, batch=args.batch)
        held = (f", {result['already_held']} already held" if result["already_held"] else "")
        print(f"{result['proposed']} proposed, {result['accepted']} accepted, "
              f"{result['rejected']} rejected{held}")
        if result["failures"]:
            print("  " + "  ".join(f"{k} {v}" for k, v in result["failures"].items()))
        if result["annotation_conflicts"]:
            print(f"  {result['annotation_conflicts']} annotation identity conflicts; "
                  "existing annotations preserved, reader identity repair still required")
        if result["calls_without_an_answer"]:
            # Not zero claims. A call with no valid answer says nothing about its chunk.
            print(f"  {result['calls_without_an_answer']} call(s) returned no valid answer and are "
                  f"not counted as chunks without claims")
        print("  read the rejections before quoting the rate: "
              "`extract-report --show-rejected`")
        return 0

    result = extract.build(project, store, batch=args.batch, limit=args.limit, kind=args.kind)
    print(f"batch {result['batch']}: {result['units']} work units over {result['chunks']} chunks "
          f"of {result['sources']} confirmed sources")
    if result["by_kind"]:
        print("  " + "  ".join(f"{k} {v}" for k, v in sorted(result["by_kind"].items())))
    print(f"  {result['prompt_chars']:,} prompt characters "
          f"\u2248 {result['prompt_chars'] // 4:,} tokens in, "
          f"{result['units'] * extract.MAX_OUTPUT_TOKENS:,} capped out")
    print(f"  drain with: claimstone model-run {args.project} extract "
          f"--batch {result['batch']} --backend <name>")
    return 0


def _extract_report(args: argparse.Namespace) -> int:
    from claimstone import extract_report

    project = load_project(args.project)
    summary = extract_report.summarise(_checked_store(args, project), batch=args.batch,
                                       project=project)

    if args.json:
        import json

        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    rate = "\u2014" if summary["gate_rate"] is None else f"{summary['gate_rate']:.2f}"
    print(f"{project.name} extract/{summary['batch'] or 'all'}")
    print(f"  proposed     {summary['proposed']:>5}   accepted {summary['accepted']}  {rate}   "
          f"rejected {summary['rejected']}")
    coverage = ("\u2014" if summary["coverage"] is None else f"{summary['coverage']:.2f}")
    print(f"  coverage     {summary['questions_with_a_claim']:>5}/{summary['questions_asked']}  "
          f"{coverage}   questions that can receive a verdict and have a claim")
    for question_id, bucket in summary["by_question"].items():
        print(f"    {question_id:<5} {bucket['claims']:>3} claims from {bucket['studies']:>2} "
              f"studies   {bucket['stances']}   {bucket['by_class']}")
    if summary["questions_without_a_claim"]:
        missing = summary["questions_without_a_claim"]
        print(f"  no claim yet  {', '.join(missing[:14])}"
              + (f" and {len(missing) - 14} more" if len(missing) > 14 else ""))
        print("                a question with no claim after a complete round is "
              "UNANSWERED_IN_LITERATURE; one whose calls never ran is NEVER_ASKED")
    if summary["failures"]:
        print("  rejected     " + "  ".join(f"{k} {v}" for k, v in summary["failures"].items()))
    if summary["superseded_rejections"]:
        print(f"  superseded   {summary['superseded_rejections']:>5}   rejections a corrected reading "
              f"turned into claims; the rows stay, and this is what the change was worth")
    print()
    print("  The two ratios are never fused: a clean gate on a silent corpus would read like a "
          "well-covered one.")
    if args.show_rejected:
        from claimstone import claim_records

        store = _checked_store(args, project)
        print()
        for row in claim_records.current(store)[1].values():
            print(f"  {row.get('chunk_id')}  {row.get('failure')}")
            print(f"    {row.get('detail')}")
            print(f"    claim: {str((row.get('record') or {}).get('claim'))[:100]}")
            print(f"    quote: {str((row.get('record') or {}).get('evidence_quote'))[:100]}")
    return 0


def _review(args: argparse.Namespace) -> int:
    from claimstone import review

    project = load_project(args.project)
    store = _checked_store(args, project)

    if args.harvest:
        # No socket, and no other ledger touched: claims.jsonl is append-only and belongs to stage 4.
        try:
            result = review.harvest(project, store, batch=args.batch)
        except review.SameReader as exc:
            print(str(exc), file=sys.stderr)
            return 2
        held = f", {result['already_held']} already held" if result["already_held"] else ""
        print(f"{result['reviewed']} reviewed{held}")
        if result["verdicts"]:
            print("  " + "  ".join(f"{k} {v}" for k, v in result["verdicts"].items()))
        if result["calls_without_an_answer"]:
            print(f"  {result['calls_without_an_answer']} call(s) returned no verdict; those claims are "
                  f"awaiting review, which is neither supported nor unsupported")
        return 0

    reviewer = None
    if args.reviewer:
        if "/" not in args.reviewer:
            print("--reviewer takes backend/model, e.g. claude-cli/claude-opus-5", file=sys.stderr)
            return 2
        backend, _, model = args.reviewer.partition("/")
        reviewer = (backend, model)

    result = review.build(project, store, batch=args.batch, reviewer=reviewer, limit=args.limit,
                          question_id=args.question)
    print(f"batch {result['batch']}: {result['units']} review units")
    if result["same_reader"]:
        print(f"  {result['same_reader']} claim(s) excluded: {args.reviewer} extracted them, and a second "
              f"opinion from the same opinion is not a control")
    for name in ("missing_chunk", "unknown_question"):
        if result[name]:
            print(f"  {result[name]} skipped: {name.replace('_', ' ')}")
    print(f"  {result['prompt_chars']:,} prompt characters "
          f"\u2248 {result['prompt_chars'] // 4:,} tokens in")
    print(f"  drain with: claimstone model-run {args.project} review "
          f"--batch {result['batch']} --backend <name>")
    return 0


def _review_report(args: argparse.Namespace) -> int:
    from claimstone import review_report

    project = load_project(args.project)
    summary = review_report.summarise(_checked_store(args, project))

    if args.json:
        import json

        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    print(f"{project.name} — {summary['claims']} claims, {summary['reviewed']} reviewed, "
          f"{summary['awaiting_review']} awaiting")
    for reader, bucket in summary["by_extractor"].items():
        share = ("\u2014" if bucket["supported_share"] is None
                 else f"{bucket['supported_share']:.2f}")
        print(f"  extracted by {reader}")
        print(f"    {bucket['verified_useful']:>4} verified useful of {bucket['reviewed']} reviewed  "
              f"{share}   {bucket['verdicts'] or '-'}")
        if bucket["awaiting_review"]:
            print(f"    {bucket['awaiting_review']:>4} awaiting review — neither supported nor "
                  f"unsupported, and stage 6 may not use them")
        if bucket["gate_rejections"]:
            print(f"    {bucket['gate_rejections']:>4} rejected by the gate  "
                  f"{bucket['gate_rejections_by_reason']}")
    if summary["reviewed_by"]:
        print(f"  reviewed by  {', '.join(summary['reviewed_by'])}")
    print()
    print(f"  {summary['caveat']}")
    return 0


def _not_implemented(args: argparse.Namespace) -> int:
    print(
        f"stage '{args.stage_name}' is not implemented yet — see README.md, 'The six stages'",
        file=sys.stderr,
    )
    return 2


def _synthesize(args: argparse.Namespace) -> int:
    from claimstone import synthesize

    project = load_project(args.project)
    store = _checked_store(args, project)
    try:
        result = synthesize.build(project, store, round_name=args.round,
                                  manifest_only=args.manifest_only)
    except synthesize.NotAdmissible as exc:
        # Invariant 3: no profiles at all, and no flag that overrides it. A corpus read below its floor
        # that certifies itself complete is worse than no corpus.
        print(str(exc), file=sys.stderr)
        print("no profiles written; the losses are in `report` by failure class", file=sys.stderr)
        return 3

    kinds = "  ".join(f"{k} {v}" for k, v in result["by_kind"].items())
    print(f"{result['profiles']} profile(s) over {result['questions']} question(s): {kinds}")
    if result["not_applicable"]:
        print(f"  {result['not_applicable']} operational question(s) recorded "
              f"LITERATURE_VERDICT_NOT_APPLICABLE rather than omitted")
    if result["no_verified_claim"]:
        print(f"  {result['no_verified_claim']} with NO_VERIFIED_CLAIM — which is not NEVER_ASKED, "
              f"and not a verdict")
    if result["provisional"]:
        print(f"  {result['provisional']} provisional and therefore not adjudicable")
    # Mandatory disclosure, and never a correction: there is nothing to correct.
    print(f"  no controlled family-wise error rate across the "
          f"{result['no_controlled_error_rate_across']} questions profiled")
    print("  no verdict was produced here; `adjudicate` is the only command that writes one")
    return 0


def _verdicts(args: argparse.Namespace) -> int:
    import json

    from claimstone import evidence, synthesize

    project = load_project(args.project)
    store = _checked_store(args, project)
    result = synthesize.verdicts(store, project=project, round_name=args.round,
                                 manifest_only=args.manifest_only)
    if not result["rows"]:
        print("no profiles; run synthesize first")
        return 0
    if args.json:
        print(json.dumps(result, indent=1, ensure_ascii=False, default=str))
        return 0

    for row in result["rows"]:
        profile = row["profile"]
        if args.question and str(profile.get("question_id")) != args.question:
            continue
        if profile.get("state") == evidence.NOT_APPLICABLE:
            print(f"{profile['question_id']:5} {profile.get('kind', ''):15} "
                  f"{evidence.NOT_APPLICABLE}")
            print(f"  reason   {profile.get('reason')}")
            continue
        flag = ""
        if row["unavailable"]:
            flag = "historical profile — " + row["unavailable"]
        elif profile.get("provisional"):
            flag = f"provisional — {', '.join(profile.get('blocking') or [])}"
        elif profile.get("state"):
            flag = str(profile["state"])
        print(f"{profile['question_id']:5} {profile.get('kind', ''):15} {flag}")
        if row["stored_profile_stale"] and not row["unavailable"]:
            print("    stored profile differs; showing current evidence, run synthesize before signing")
        completion = profile.get("extraction") or {}
        if completion:
            print(f"    extraction       {completion['expected']} expected readings; "
                  f"{completion['unanswered']} unanswered, {completion['unharvested']} unharvested"
                  f", {completion['unregated']} annotations awaiting the current gate")
        for result_row in profile.get("results", [])[: args.results]:
            figure = result_row.get("estimate_as_written") or result_row.get("contrast_as_written") or ""
            print(f"    {str(result_row.get('source_id')):8} {str(result_row.get('stance')):11} "
                  f"{str(figure)[:22]:22} {str(result_row.get('sample') or '')[:34]}")
        extra = len(profile.get("results", [])) - args.results
        if extra > 0:
            print(f"    … {extra} more")
        counts = profile.get("direction_count") or {}
        if counts:
            print("    direction count  "
                  + "  ".join(f"{k} {v}" for k, v in counts.items())
                  + "   (a count, not a strength)")
        print(f"    linkage          {profile.get('linkage')}"
              + (f": {len(profile.get('sample_labels') or [])} sample label(s), verbatim"
                 if profile.get("sample_labels") else ""))
        coverage = profile.get("coverage") or {}
        print(f"    coverage         {coverage.get('sources')} of {coverage.get('examined')} "
              f"examined source(s)")
        rejected = profile.get("gate_rejected") or {}
        if rejected:
            print("    gate rejected    "
                  + "  ".join(f"{k} {v}" for k, v in rejected.items()))
        if profile.get("awaiting_review"):
            print(f"    awaiting review  {profile['awaiting_review']}")
        if profile.get("reviewed_not_usable"):
            print("    read, not used   "
                  + "  ".join(f"{k} {v}" for k, v in profile["reviewed_not_usable"].items()))
        recorded = row["verdict"]
        if recorded and row["stale"]:
            print(f"    VERDICT (STALE)  {recorded['verdict']} — recorded against profile "
                  f"{str(recorded.get('profile_sha256'))[:12]}, current "
                  f"{str(profile.get('profile_sha256'))[:12]}")
        elif recorded:
            print(f"    VERDICT          {recorded['verdict']} — {recorded.get('adjudicated_by')}, "
                  f"{recorded.get('adjudicated_at')}")

    print(f"\n{result['adjudicated']} adjudicated, {result['stale']} stale, "
          f"{result['awaiting_adjudication']} awaiting a person")
    print(f"no controlled family-wise error rate across the "
          f"{result['no_controlled_error_rate_across']} questions")
    return 0


def _adjudicate(args: argparse.Namespace) -> int:
    import pathlib

    from claimstone import synthesize

    project = load_project(args.project)
    store = _checked_store(args, project)
    rationale = pathlib.Path(args.rationale_file).read_text(encoding="utf-8")
    try:
        row = synthesize.adjudicate(store, args.question, project=project, verdict=args.verdict,
                                    round_name=args.round, manifest_only=args.manifest_only,
                                    rationale=rationale, by=args.by,
                                    signer_auth="cli-declared", actor=None,
                                    profile_sha256=args.profile_sha256 or "")
    except (synthesize.NotAdmissible, synthesize.Provisional, synthesize.StaleProfile, ValueError, KeyError) as exc:
        print(str(exc).strip("'"), file=sys.stderr)
        return 2
    print(f"{row['question_id']}: {row['verdict']} against profile "
          f"{row['profile_sha256'][:12]}, by {row['adjudicated_by']}")
    return 0


def _serve(args: argparse.Namespace) -> int:
    from claimstone import dashboard

    project = load_project(args.project)
    store = _checked_store(args, project)
    warning = dashboard.host_warning(args.host)
    if warning:
        # §10: a non-loopback bind is accepted only because --host was passed explicitly, and the
        # warning names the rule rather than mumbling about security.
        print(f"warning: {warning}", file=sys.stderr)
    dashboard.serve(project, store, round_name=args.round, manifest_only=args.manifest_only,
                    host=args.host, port=args.port)
    return 0


def _flow_open(args: argparse.Namespace) -> tuple["Project", "Store"]:
    """The store without `_checked_store`'s recording: flow reads never write, and a drift is a
    state the command reports, not a crash (spec §3.6)."""
    from claimstone.store import Store

    project = load_project(args.project)
    return project, Store(project.name, base=args.store)


def _scheduler_preview(args: argparse.Namespace) -> int:
    import json

    from claimstone import scheduler_preview
    from claimstone.store import LedgerCorrupt

    project, store = _flow_open(args)
    try:
        result = scheduler_preview.preview(project, store, args.flow_id)
    except (ValueError, LedgerCorrupt) as exc:
        # Preserve a nonzero exit on a damaged ledger or unknown flow. No command
        # can treat an omitted preview as an empty, executable plan.
        print(f"scheduler preview refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def _scheduler_operation(args: argparse.Namespace) -> int:
    import json
    import pathlib
    from claimstone import autopilot, copy_policy, network_schedule, operations, periodic, periodic_dossier
    from claimstone.store import LedgerCorrupt

    project, store = _flow_open(args)
    try:
        if args.scheduler_command == 'plan':
            reviewer = None
            if args.reviewer:
                backend, slash, model = args.reviewer.partition('/')
                if not slash or not backend or not model:
                    raise operations.OperationError('--reviewer requires backend/model')
                reviewer = (backend, model)
            result = operations.plan(project, store, args.flow_id, args.stage,
                                     batch=args.batch, reviewer=reviewer,
                                     model=args.model, max_calls=args.max_calls,
                                     backend=args.backend, budget_id=args.budget_id,
                                     budget_cents=args.budget_cents,
                                     max_call_cents=args.max_call_cents,
                                     price_in_cents=args.price_in_cents,
                                     price_out_cents=args.price_out_cents,
                                     candidate_key=args.candidate_key,
                                     allowed_hosts=args.allow_host,
                                     max_requests=args.max_requests,
                                     api=args.api, topic_id=args.topic,
                                     term=args.term, per_query=args.per_query,
                                     run_label=args.run_label,
                                     use_apis=args.use_apis,
                                     retry_classes=args.retry_class,
                                     retry_reason=args.retry_reason)
            result = {'operation_id': operations._digest(result), 'plan': result}
        elif args.scheduler_command == 'batch-plan':
            result = operations.plan_batch(project, store, args.flow_id, args.stage,
                                           apis=args.api, allowed_hosts=args.allow_host,
                                           max_units=args.max_units,
                                           max_requests_each=args.max_requests_each,
                                           per_query=args.per_query,
                                           use_apis=args.use_apis,
                                           retry_classes=args.retry_class,
                                           retry_reason=args.retry_reason)
        elif args.scheduler_command == 'authorize-batch':
            result = operations.authorize_batch(store, args.batch_id)
        elif args.scheduler_command == 'schedule-plan':
            entries = json.loads(pathlib.Path(args.entries_file).read_text(encoding='utf-8'))
            result = network_schedule.plan(store, project.name, entries,
                                           max_total_requests=args.max_total_requests)
        elif args.scheduler_command == 'periodic-plan':
            rounds = json.loads(pathlib.Path(args.rounds_file).read_text(encoding='utf-8'))
            result = periodic.plan(project, store, args.source_flow_id, rounds,
                                   apis=args.api, allowed_hosts=args.allow_host,
                                   max_units_each=args.max_units_each,
                                   max_requests_each=args.max_requests_each,
                                   per_query=args.per_query)
        elif args.scheduler_command == 'periodic-audit':
            result = periodic.audit(project, store, args.schedule_id)
        elif args.scheduler_command == 'periodic-dossier':
            result = periodic_dossier.preview(project, store, args.schedule_id)
        elif args.scheduler_command == 'periodic-finalize':
            result = periodic_dossier.finalize(project, store, args.schedule_id)
        elif args.scheduler_command == 'copy-policy-plan':
            result = copy_policy.plan(project, store, args.schedule_id,
                                      allowed_hosts=args.allow_host,
                                      source_classes=args.source_class,
                                      max_candidates=args.max_candidates,
                                      max_requests_each=args.max_requests_each,
                                      not_before=args.not_before,
                                      expires_at=args.expires_at)
        elif args.scheduler_command == 'copy-policy-authorize':
            result = copy_policy.authorize(store, args.policy_id)
        elif args.scheduler_command == 'copy-policy-revoke':
            result = copy_policy.revoke(store, args.policy_id)
        elif args.scheduler_command == 'copy-policy-status':
            result = copy_policy.status(store, args.policy_id)
        elif args.scheduler_command == 'schedule-authorize':
            result = network_schedule.authorize(store, args.schedule_id)
        elif args.scheduler_command == 'schedule-revoke':
            result = network_schedule.revoke(store, args.schedule_id)
        elif args.scheduler_command == 'schedule-status':
            result = network_schedule.status(store, args.schedule_id)
        elif args.scheduler_command == 'drive':
            result = operations.drive_local(project, store, args.flow_id,
                                            extract_model=args.extract_model,
                                            review_model=args.review_model,
                                            max_local_calls=args.max_local_calls)
        elif args.scheduler_command == 'auto-enable':
            result = autopilot.enable(project, store, args.flow_id,
                                      extract_model=args.extract_model,
                                      review_model=args.review_model,
                                      max_total_local_calls=args.max_total_local_calls,
                                      discover_apis=args.discover_api,
                                      discover_hosts=args.discover_host,
                                      acquire_hosts=args.acquire_host,
                                      proposal_max_units=args.proposal_max_units,
                                      proposal_max_requests_each=args.proposal_max_requests_each,
                                      proposal_per_query=args.proposal_per_query)
        elif args.scheduler_command == 'auto-disable':
            result = autopilot.disable(store, args.mandate_id)
        elif args.scheduler_command == 'auto-status':
            result = autopilot.status(store, args.mandate_id)
        elif args.scheduler_command == 'auto-once':
            result = autopilot.tick(project, store, args.mandate_id)
        elif args.scheduler_command == 'auto-worker':
            import signal
            import threading
            if args.poll_seconds < 1:
                raise operations.OperationError('--poll-seconds must be at least 1')
            print('local mandate worker running; Ctrl-C stops after the current pass',
                  file=sys.stderr)
            stopping = threading.Event()
            previous_sigterm = signal.signal(signal.SIGTERM,
                                             lambda signum, frame: stopping.set())
            try:
                while not stopping.is_set():
                    result = autopilot.tick(load_project(args.project), store,
                                            args.mandate_id)
                    if (result.get('local_calls') or result.get('network', {}).get('processed') or
                            any(item['new'] for item in result.get('proposals', [])) or
                            any(item['new'] for item in result.get('periodic_dossiers', []))):
                        print(json.dumps(result, ensure_ascii=False), flush=True)
                    stopping.wait(args.poll_seconds)
            except KeyboardInterrupt:
                pass
            finally:
                signal.signal(signal.SIGTERM, previous_sigterm)
            return 0
        elif args.scheduler_command == 'authorize':
            result = operations.authorize(store, args.operation_id)
        elif args.scheduler_command == 'run':
            result = operations.execute(project, store, args.operation_id)
        elif args.scheduler_command == 'tick':
            result = operations.tick(project, store, max_operations=args.max_operations)
        elif args.scheduler_command == 'worker':
            import signal
            import threading
            if args.poll_seconds < 1:
                raise operations.OperationError('--poll-seconds must be at least 1')
            print('scheduler worker running; Ctrl-C stops after the current operation',
                  file=sys.stderr)
            stopping = threading.Event()
            previous_sigterm = signal.signal(signal.SIGTERM,
                                             lambda signum, frame: stopping.set())
            try:
                while not stopping.is_set():
                    tick_result = operations.tick(load_project(args.project), store,
                                                  max_operations=args.max_operations)
                    if tick_result['processed']:
                        print(json.dumps(tick_result, ensure_ascii=False), flush=True)
                    stopping.wait(args.poll_seconds)
            except KeyboardInterrupt:
                pass
            finally:
                signal.signal(signal.SIGTERM, previous_sigterm)
            return 0
        else:
            result = operations.status(store, args.operation_id)
    except (operations.OperationError, LedgerCorrupt, ValueError) as exc:
        print(f'scheduler refused: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def _flow_create(args: argparse.Namespace) -> int:
    from claimstone import flows, scope

    project, store = _flow_open(args)
    try:
        row, created = flows.create(
            project, store, selector=scope.Selector(args.round, args.manifest),
            title=args.title, derived_from=args.derived_from, relation=args.relation)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"{'created' if created else 'exists'} {row['flow_id']}")
    if row.get("bound_after_data"):
        print("warning: bound after data existed: rows written before binding are not "
              "verified against this protocol")
    return 0


def _flow_list(args: argparse.Namespace) -> int:
    import json as _json

    from claimstone import flows
    from claimstone.config import RegistryDrift, check_registry_drift

    project, store = _flow_open(args)
    drift = None
    try:
        check_registry_drift(project, store, record=False)
    except RegistryDrift as exc:
        drift = str(exc)
    rows = flows.flows(store)
    listed = []
    for flow_id, row in sorted(rows.items()):
        state = flows.binding_state(project, store, row)
        selector = (row.get("binding") or {}).get("selector") or {}
        listed.append({
            "flow_id": flow_id,
            "selector": selector,
            "title": row.get("title"),
            "binding_state": state["state"],
            "differences": state["differences"],
            "bound_after_data": bool(row.get("bound_after_data")),
        })
    legacy = [selector.round for selector in flows.legacy_selectors(store, rows.values())]

    if args.json:
        print(_json.dumps({"flows": listed, "legacy_selectors": legacy,
                           "registry_drift": drift}, indent=1, ensure_ascii=False, default=str))
        return 0
    if drift:
        print(f"registry drift: {drift}")
    for entry in listed:
        selector = entry["selector"]
        name = selector.get("round") or "(whole store)"
        flag = " manifest-only" if selector.get("manifest_only") else ""
        title = f"  {entry['title']}" if entry["title"] else ""
        print(f"{entry['flow_id'][:12]}  {name}{flag}  {entry['binding_state']}{title}")
        if entry["differences"]:
            print(f"    differs in: {', '.join(entry['differences'])}")
    for name in legacy:
        print(f"legacy {name}: protocol not verified")
    return 0


def _flow_check(args: argparse.Namespace) -> int:
    from claimstone import flows
    from claimstone.config import RegistryDrift, check_registry_drift

    project, store = _flow_open(args)
    row = flows.flows(store).get(args.flow_id)
    if row is None:
        print(f"unknown flow id: {args.flow_id}", file=sys.stderr)
        return 2
    drift = None
    try:
        check_registry_drift(project, store, record=False)
    except RegistryDrift as exc:
        drift = str(exc)
    state = flows.binding_state(project, store, row)
    print(state["state"])
    if state["differences"]:
        print(f"  differs in: {', '.join(state['differences'])}")
    if drift:
        print(f"  registry drift: {drift}")
    if state["bound_after_data"]:
        print("  bound after data existed: rows written before binding are not verified "
              "against this protocol")
    return 0 if state["state"] == "CURRENT" and drift is None else 4


def _flow_title(args: argparse.Namespace) -> int:
    import getpass

    from claimstone import flows

    project, store = _flow_open(args)
    try:
        flows.set_title(store, args.flow_id, args.title,
                        by=args.by or getpass.getuser())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"title set on {args.flow_id[:12]}")
    return 0


def _portal(args: argparse.Namespace) -> int:
    from claimstone import dashboard, portal

    warning = dashboard.host_warning(args.host)
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    portal.serve(args.projects_dir, args.store, host=args.host, port=args.port,
                 allow_hosts=tuple(args.allow_host))
    return 0


def _api(args: argparse.Namespace) -> int:
    from claimstone import api, dashboard

    warning = dashboard.host_warning(args.host)
    if warning:
        # §10, as with portal and serve: an explicit non-loopback bind proceeds with the warning.
        print(f"warning: {warning}", file=sys.stderr)
    api.serve(args.projects_dir, args.store, host=args.host, port=args.port,
              allow_hosts=tuple(args.allow_host))
    return 0


def _control(args: argparse.Namespace) -> int:
    from claimstone import control

    try:
        control.serve(args.projects, args.store, host=args.bind, port=args.port,
                      allow_hosts=tuple(args.allow_host), state_dir=args.state_dir,
                      env_file=args.credentials_file)
    except ValueError as exc:
        # The refused non-loopback bind: this process writes, so unlike the read-only
        # servers it does not proceed on a warning (spec B4).
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _operator(args: argparse.Namespace) -> int:
    import getpass

    from claimstone import operators

    directory = operators.state_dir()
    try:
        if args.operator_command == "add":
            password = getpass.getpass("password: ")
            if password != getpass.getpass("again: "):
                print("passwords do not match", file=sys.stderr)
                return 2
            operators.add_operator(directory, args.id, args.name, password)
            print(f"operator recorded: {args.id} ({args.name}) in {directory}/")
        elif args.operator_command == "disable":
            operators.disable_operator(directory, args.id)
            print(f"operator disabled: {args.id}")
        else:  # argparse makes this unreachable; kept honest anyway
            return 2
    except operators.OperatorError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def _export(args: argparse.Namespace) -> int:
    import pathlib

    from claimstone import export as export_mod
    from claimstone.store import Store

    project = load_project(args.project)
    store = Store(project.name, base=args.store)
    try:
        directory, created = export_mod.export(project, store, args.flow_id)
    except (ValueError, ConfigError) as exc:  # ConfigError includes RegistryDrift
        print(str(exc), file=sys.stderr)
        return 2
    print(f"{'created' if created else 'exists'} {directory.name}")
    print(str(pathlib.Path(directory).relative_to(store.root)) if str(directory).startswith(
        str(store.root)) else str(directory))
    return 0


def _export_verify(args: argparse.Namespace) -> int:
    import pathlib

    from claimstone import export as export_mod

    problems = export_mod.verify(pathlib.Path(args.dir), args.projects_dir)
    for problem in problems:
        print(problem)
    if not problems:
        print("verified: prefixes unchanged and outputs recompute identically")
    return 0 if not problems else 5





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
        ("discover", _discover, "stage 1: topics and citations become candidates"),
        ("discover-report", _discover_report, "what the two channels found"),
        ("regate", _regate, "re-judge bytes already held under the current gate; no network"),
        ("normalize", _normalize, "stage 3: TEI, chunks and references"),
        ("extract", _extract, "stage 4: build the work units, or --harvest the answers"),
        ("extract-report", _extract_report, "the gate's ratio and the corpus's, never fused"),
        ("review", _review, "stage 5: build the review units, or --harvest the verdicts"),
        ("review-report", _review_report, "verdicts per extraction reader; precision side only"),
        ("synthesize", _synthesize, "stage 6: an evidence profile per question, or the refusal"),
        ("verdicts", _verdicts, "the profiles, with any adjudication and whether it is stale"),
        ("adjudicate", _adjudicate, "record one person's verdict; the only place one comes from"),
        ("serve", _serve, "the dashboard: a read-only page over this round's ledgers"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("project", help="path to a project directory")
        command.add_argument("--store", default="store", help="where generated data lives")
        command.set_defaults(func=handler)
        if name == 'gate-audit':
            command.add_argument('--round', default=None, help='audit one declared population')
            command.add_argument('--manifest', action='store_true', help='audit the curated manifest')
        if name == "import-manifest":
            command.add_argument("--round", default="manifest",
                                 help="name this import; it lands on every candidate, and the floor "
                                      "is judged per round")
        if name == "acquire":
            command.add_argument("--campaign", help="name this run; required with --retry-class")
            command.add_argument("--round", default=None,
                                 help="attempt only this round's candidates")
            command.add_argument("--manifest", action="store_true",
                                 help="attempt only the sources the manifest declared, which is the "
                                      "population a curated corpus's floor is about")
            command.add_argument("--only-oa", action="store_true",
                                 help="attempt only candidates whose discovery metadata already "
                                      "records a free copy; absent is unknown, not closed")
            command.add_argument("--retry-class", action="append",
                                 help="re-request a terminal failure class, e.g. PAYWALL_403")
            command.add_argument("--limit", type=int, default=None)
            command.add_argument("--no-apis", action="store_true",
                                 help="plan from the candidate URL alone; no Unpaywall or OpenAlex")
            command.add_argument("--dry-run", action="store_true",
                                 help="print the planned cascade and fetch nothing")
        if name == "report":
            command.add_argument("--json", action="store_true")
            command.add_argument("--round", default=None,
                                 help="judge one round's candidates; default every candidate held")
            command.add_argument("--manifest", action="store_true",
                                 help="judge only the sources the manifest declared, which is the "
                                      "population a curated corpus's floor is about")
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
        if name == "discover":
            command.add_argument("--round", default="routine",
                                 help="name this round; it lands on every candidate")
            command.add_argument("--topics", help="comma-separated topic ids; default all")
            command.add_argument("--api", action="append",
                                 help=f"repeatable; one of {', '.join(APIS)}. Default all")
            command.add_argument("--per-query", type=int, default=25)
            command.add_argument("--channel", choices=("keyword", "citation", "both"),
                                 default="both")
            command.add_argument("--promote-contested", action="store_true",
                                 help="admit works named in rejected secondhand claims, whatever the "
                                      "citation threshold says; no request")
            command.add_argument("--reclassify", action="store_true",
                                 help="re-apply sources.yaml's assign_when rules to held candidates; "
                                      "no request, for when the rules changed")
            command.add_argument("--resolve", action="store_true",
                                 help="look up each admitted reference's venue and address; "
                                      "makes requests, so the citation channel is offline without it")
        if name == "discover-report":
            command.add_argument("--round", default=None, help="isolate one round")
            command.add_argument("--json", action="store_true")
        if name == "extract":
            command.add_argument("--batch", required=True, help="which batch to build or harvest")
            command.add_argument("--harvest", action="store_true",
                                 help="gate the drained answers into the two ledgers; no request")
            command.add_argument("--limit", type=int, default=None,
                                 help="chunks per kind, not units in total")
            command.add_argument("--kind", default=None,
                                 help="build one kind alone: " + ", ".join(extract_kinds()))
        if name == "review":
            command.add_argument("--batch", required=True, help="which batch to build or harvest")
            command.add_argument("--harvest", action="store_true",
                                 help="write reviews.jsonl from the drained verdicts; no request")
            command.add_argument("--reviewer",
                                 help="backend/model that will be asked, so the claims it may not "
                                      "judge are excluded before the calls are paid for")
            command.add_argument("--question", default=None,
                                 help="one question's claims, which is what one adjudicable profile "
                                      "needs; a verdict is per question")
            command.add_argument("--limit", type=int, default=None)
        if name in ("synthesize", "verdicts", "adjudicate"):
            command.add_argument("--round", default=None,
                                 help="judge the floor over one round; a discovery sweep changes the "
                                      "denominator by design (D24)")
            command.add_argument("--manifest-only", action="store_true",
                                 help="judge the floor over the operator's reading list alone")
        if name == "verdicts":
            command.add_argument("--question", default=None, help="one question alone")
            command.add_argument("--json", action="store_true")
            command.add_argument("--results", type=int, default=8,
                                 help="how many results to print per profile")
        if name == "adjudicate":
            command.add_argument("question", help="which question this judges")
            command.add_argument("--verdict", required=True,
                                 help="one of " + ", ".join(VERDICT_NAMES))
            command.add_argument("--rationale-file", required=True,
                                 help="the reasoning, which is the verdict's only defence")
            command.add_argument("--by", required=True, help="who is signing this")
            command.add_argument("--profile-sha256", required=True,
                                 help="the profile hash you were shown; refused if it has moved")
        if name == "review-report":
            command.add_argument("--json", action="store_true")
        if name == "extract-report":
            command.add_argument("--batch", default=None, help="one batch; default every claim held")
            command.add_argument("--show-rejected", action="store_true",
                                 help="every rejection with its failed check, for a by-hand read")
            command.add_argument("--json", action="store_true")
        if name == "normalize":
            command.add_argument("--grobid-url", default=grobid_url_default())
            command.add_argument("--force", action="store_true",
                                 help="re-chunk from what is already parsed; no network")
            command.add_argument("--limit", type=int, default=None)
            command.add_argument("--confirm-audit", action="store_true",
                                 help="sweep a confirmation threshold; needs no GROBID")
            command.add_argument("--sweep", choices=sorted(CONFIRM_SWEEP_VALUES),
                                 help="which threshold --confirm-audit moves")
        if name == "serve":
            command.add_argument("--port", type=int, default=8787)
            command.add_argument("--host", default="127.0.0.1",
                                 help="loopback only by default; a non-loopback bind prints the "
                                      "privacy warning and proceeds because you asked")
            command.add_argument("--round", default=None,
                                 help="one declared round; default every candidate held")
            command.add_argument("--manifest-only", action="store_true",
                                 help="the operator's reading list alone, as synthesize judges it")

    flow = sub.add_parser("flow", help="bind round selectors to the protocol digests they ran under")
    flow_sub = flow.add_subparsers(dest="flow_command", required=True)
    flow_create = flow_sub.add_parser("create", help="bind one selector to the protocol now")
    flow_create.add_argument("project", help="path to a project directory")
    flow_create.add_argument("--store", default="store", help="where generated data lives")
    flow_create.add_argument("--title", required=True, help="display name; metadata only")
    flow_create.add_argument("--round", default=None,
                             help="the round this flow is; default the whole store")
    flow_create.add_argument("--manifest", action="store_true",
                             help="the operator's reading list alone")
    flow_create.add_argument("--derived-from", default=None,
                             help="an existing flow id this one replaces or extends")
    flow_create.add_argument("--relation", choices=("supersedes", "derived_from"), default=None,
                             help="how --derived-from relates to this flow")
    flow_create.set_defaults(func=_flow_create)
    flow_list = flow_sub.add_parser("list", help="every flow and its binding state; then legacies")
    flow_list.add_argument("project", help="path to a project directory")
    flow_list.add_argument("--store", default="store", help="where generated data lives")
    flow_list.add_argument("--json", action="store_true")
    flow_list.set_defaults(func=_flow_list)
    flow_check = flow_sub.add_parser("check", help="one flow against the live protocol")
    flow_check.add_argument("project", help="path to a project directory")
    flow_check.add_argument("flow_id", help="the 64-hex flow id")
    flow_check.add_argument("--store", default="store", help="where generated data lives")
    flow_check.set_defaults(func=_flow_check)
    flow_title = flow_sub.add_parser("title", help="rename a flow; metadata only")
    flow_title.add_argument("project", help="path to a project directory")
    flow_title.add_argument("flow_id", help="the 64-hex flow id")
    flow_title.add_argument("--store", default="store", help="where generated data lives")
    flow_title.add_argument("--title", required=True, help="the new display name")
    flow_title.add_argument("--by", default=None, help="who renamed it; default this user")
    flow_title.set_defaults(func=_flow_title)

    scheduler_cmd = sub.add_parser(
        "scheduler-preview", help="read-only next-work preview for one bound flow")
    scheduler_cmd.add_argument("project", help="path to a project directory")
    scheduler_cmd.add_argument("flow_id", help="the 64-hex flow id")
    scheduler_cmd.add_argument("--store", default="store", help="where generated data lives")
    scheduler_cmd.set_defaults(func=_scheduler_preview)

    scheduler = sub.add_parser('scheduler', help='bounded operations for a protocol-bound flow')
    scheduler_sub = scheduler.add_subparsers(dest='scheduler_command', required=True)
    scheduler_plan = scheduler_sub.add_parser('plan', help='freeze one scoped offline stage')
    scheduler_plan.add_argument('project')
    scheduler_plan.add_argument('flow_id')
    scheduler_plan.add_argument('stage', choices=('normalize', 'extract-build',
                                                  'extract-drain', 'extract-harvest',
                                                  'review-build', 'review-drain',
                                                  'review-harvest', 'synthesize',
                                                  'acquire', 'discover'))
    scheduler_plan.add_argument('--batch')
    scheduler_plan.add_argument('--reviewer', help='backend/model for review-build')
    scheduler_plan.add_argument('--model', help='exact model for a drain plan')
    scheduler_plan.add_argument('--backend', choices=('llamacpp', 'ollama-cloud'),
                                default='llamacpp')
    scheduler_plan.add_argument('--max-calls', type=int, help='maximum model calls')
    scheduler_plan.add_argument('--budget-id', help='persistent paid budget name')
    scheduler_plan.add_argument('--budget-cents', type=int,
                                help='cumulative authorized reservation ceiling in USD cents')
    scheduler_plan.add_argument('--max-call-cents', type=int,
                                help='conservative reservation per remote call in USD cents')
    scheduler_plan.add_argument('--price-in-cents', type=int,
                                help='declared input price ceiling in USD cents per million tokens')
    scheduler_plan.add_argument('--price-out-cents', type=int,
                                help='declared output price ceiling in USD cents per million tokens')
    scheduler_plan.add_argument('--candidate-key', help='exact candidate key for acquire')
    scheduler_plan.add_argument('--allow-host', action='append', default=[],
                                help='exact network host permitted; repeatable')
    scheduler_plan.add_argument('--max-requests', type=int,
                                help='physical request ceiling, including robots and redirects')
    scheduler_plan.add_argument('--api', help='one scholarly API for discover')
    scheduler_plan.add_argument('--topic', help='one topic id for discover')
    scheduler_plan.add_argument('--term', help='one exact frozen search term')
    scheduler_plan.add_argument('--per-query', type=int,
                                help='maximum results requested from the API')
    scheduler_plan.add_argument('--run-label',
                                help='new named attempt after a failed offline operation')
    scheduler_plan.add_argument('--use-apis', action='store_true',
                                help='allow the acquisition resolver’s metadata API cascade')
    scheduler_plan.add_argument('--retry-class', action='append', default=[],
                                help='explicit terminal class for one acquisition retry')
    scheduler_plan.add_argument('--retry-reason',
                                help='why a terminal acquisition or pre-transport query failure is retried')
    scheduler_plan.add_argument('--store', default='store')
    scheduler_plan.set_defaults(func=_scheduler_operation)
    scheduler_batch_plan = scheduler_sub.add_parser(
        'batch-plan', help='freeze a bounded set of one-query or one-candidate plans')
    scheduler_batch_plan.add_argument('project')
    scheduler_batch_plan.add_argument('flow_id')
    scheduler_batch_plan.add_argument('stage', choices=('discover', 'acquire'))
    scheduler_batch_plan.add_argument('--store', default='store')
    scheduler_batch_plan.add_argument('--api', action='append', default=[],
                                      help='API included in discovery; repeatable')
    scheduler_batch_plan.add_argument('--allow-host', action='append', default=[],
                                      help='exact host; repeatable')
    scheduler_batch_plan.add_argument('--max-units', type=int, required=True)
    scheduler_batch_plan.add_argument('--max-requests-each', type=int, required=True)
    scheduler_batch_plan.add_argument('--per-query', type=int, default=25)
    scheduler_batch_plan.add_argument('--use-apis', action='store_true')
    scheduler_batch_plan.add_argument('--retry-class', action='append', default=[])
    scheduler_batch_plan.add_argument('--retry-reason')
    scheduler_batch_plan.set_defaults(func=_scheduler_operation)
    scheduler_authorize_batch = scheduler_sub.add_parser(
        'authorize-batch', help='authorize every exact plan in a frozen batch')
    scheduler_authorize_batch.add_argument('project')
    scheduler_authorize_batch.add_argument('batch_id')
    scheduler_authorize_batch.add_argument('--store', default='store')
    scheduler_authorize_batch.set_defaults(func=_scheduler_operation)
    scheduler_schedule_plan = scheduler_sub.add_parser(
        'schedule-plan', help='freeze finite UTC windows for exact existing network batches')
    scheduler_schedule_plan.add_argument('project')
    scheduler_schedule_plan.add_argument('--entries-file', required=True,
                                         help='JSON array of batch_id, not_before, expires_at')
    scheduler_schedule_plan.add_argument('--max-total-requests', type=int, required=True)
    scheduler_schedule_plan.add_argument('--store', default='store')
    scheduler_schedule_plan.set_defaults(func=_scheduler_operation)
    scheduler_periodic_plan = scheduler_sub.add_parser(
        'periodic-plan', help='freeze dated new rounds and their exact discovery schedule')
    scheduler_periodic_plan.add_argument('project')
    scheduler_periodic_plan.add_argument('source_flow_id')
    scheduler_periodic_plan.add_argument('--rounds-file', required=True)
    scheduler_periodic_plan.add_argument('--api', action='append', required=True)
    scheduler_periodic_plan.add_argument('--allow-host', action='append', required=True)
    scheduler_periodic_plan.add_argument('--max-units-each', type=int, required=True)
    scheduler_periodic_plan.add_argument('--max-requests-each', type=int, required=True)
    scheduler_periodic_plan.add_argument('--per-query', type=int, default=25)
    scheduler_periodic_plan.add_argument('--store', default='store')
    scheduler_periodic_plan.set_defaults(func=_scheduler_operation)
    scheduler_periodic_audit = scheduler_sub.add_parser(
        'periodic-audit', help='inspect per-round and cumulative acquisition without a verdict')
    scheduler_periodic_audit.add_argument('project')
    scheduler_periodic_audit.add_argument('schedule_id')
    scheduler_periodic_audit.add_argument('--store', default='store')
    scheduler_periodic_audit.set_defaults(func=_scheduler_operation)
    for action, description in (
        ('periodic-dossier', 'read the live cumulative evidence handoff without writing'),
        ('periodic-finalize', 'persist eligible cumulative profiles and final dossier')):
        command = scheduler_sub.add_parser(action, help=description)
        command.add_argument('project')
        command.add_argument('schedule_id')
        command.add_argument('--store', default='store')
        command.set_defaults(func=_scheduler_operation)
    scheduler_copy_policy_plan = scheduler_sub.add_parser(
        'copy-policy-plan', help='freeze a finite copy allowance for unknown scheduled discoveries')
    scheduler_copy_policy_plan.add_argument('project')
    scheduler_copy_policy_plan.add_argument('schedule_id')
    scheduler_copy_policy_plan.add_argument('--allow-host', action='append', required=True)
    scheduler_copy_policy_plan.add_argument('--source-class', action='append', required=True)
    scheduler_copy_policy_plan.add_argument('--max-candidates', type=int, required=True)
    scheduler_copy_policy_plan.add_argument('--max-requests-each', type=int, required=True)
    scheduler_copy_policy_plan.add_argument('--not-before', required=True)
    scheduler_copy_policy_plan.add_argument('--expires-at', required=True)
    scheduler_copy_policy_plan.add_argument('--store', default='store')
    scheduler_copy_policy_plan.set_defaults(func=_scheduler_operation)
    for action in ('copy-policy-authorize', 'copy-policy-revoke', 'copy-policy-status'):
        command = scheduler_sub.add_parser(action)
        command.add_argument('project')
        command.add_argument('policy_id')
        command.add_argument('--store', default='store')
        command.set_defaults(func=_scheduler_operation)
    for action in ('schedule-authorize', 'schedule-revoke', 'schedule-status'):
        command = scheduler_sub.add_parser(action)
        command.add_argument('project')
        command.add_argument('schedule_id')
        command.add_argument('--store', default='store')
        command.set_defaults(func=_scheduler_operation)
    scheduler_drive = scheduler_sub.add_parser(
        'drive', help='one bounded local pass through scoped research stages')
    scheduler_drive.add_argument('project')
    scheduler_drive.add_argument('flow_id')
    scheduler_drive.add_argument('--store', default='store')
    scheduler_drive.add_argument('--extract-model', required=True)
    scheduler_drive.add_argument('--review-model', required=True)
    scheduler_drive.add_argument('--max-local-calls', type=int, required=True)
    scheduler_drive.set_defaults(func=_scheduler_operation)
    scheduler_auto_enable = scheduler_sub.add_parser(
        'auto-enable', help='authorize bounded recurring local work for one flow')
    scheduler_auto_enable.add_argument('project')
    scheduler_auto_enable.add_argument('flow_id')
    scheduler_auto_enable.add_argument('--store', default='store')
    scheduler_auto_enable.add_argument('--extract-model', required=True)
    scheduler_auto_enable.add_argument('--review-model', required=True)
    scheduler_auto_enable.add_argument('--max-total-local-calls', type=int, required=True)
    scheduler_auto_enable.add_argument('--discover-api', action='append', default=[],
                                       help='API for unapproved discovery proposals; repeatable')
    scheduler_auto_enable.add_argument('--discover-host', action='append', default=[],
                                       help='exact discovery host in proposed plans; repeatable')
    scheduler_auto_enable.add_argument('--acquire-host', action='append', default=[],
                                       help='exact acquisition host in proposed plans; repeatable')
    scheduler_auto_enable.add_argument('--proposal-max-units', type=int, default=10)
    scheduler_auto_enable.add_argument('--proposal-max-requests-each', type=int, default=3)
    scheduler_auto_enable.add_argument('--proposal-per-query', type=int, default=25)
    scheduler_auto_enable.set_defaults(func=_scheduler_operation)
    for action in ('auto-disable', 'auto-status', 'auto-once', 'auto-worker'):
        command = scheduler_sub.add_parser(action)
        command.add_argument('project')
        command.add_argument('mandate_id')
        command.add_argument('--store', default='store')
        if action == 'auto-worker':
            command.add_argument('--poll-seconds', type=int, default=30)
        command.set_defaults(func=_scheduler_operation)
    for action in ('authorize', 'run', 'status'):
        command = scheduler_sub.add_parser(action)
        command.add_argument('project')
        command.add_argument('operation_id')
        command.add_argument('--store', default='store')
        command.set_defaults(func=_scheduler_operation)
    scheduler_tick = scheduler_sub.add_parser('tick', help='run approved local operations')
    scheduler_tick.add_argument('project')
    scheduler_tick.add_argument('--store', default='store')
    scheduler_tick.add_argument('--max-operations', type=int, default=1)
    scheduler_tick.set_defaults(func=_scheduler_operation)
    scheduler_worker = scheduler_sub.add_parser('worker', help='poll and run approved operations')
    scheduler_worker.add_argument('project')
    scheduler_worker.add_argument('--store', default='store')
    scheduler_worker.add_argument('--max-operations', type=int, default=1)
    scheduler_worker.add_argument('--poll-seconds', type=int, default=30)
    scheduler_worker.set_defaults(func=_scheduler_operation)

    portal_cmd = sub.add_parser("portal", help="the read-only multi-project research portal")
    portal_cmd.add_argument("--projects-dir", default="projects",
                            help="every project under this directory is served")
    portal_cmd.add_argument("--store", default="store", help="where generated data lives")
    portal_cmd.add_argument("--host", default="127.0.0.1",
                            help="loopback only by default; a non-loopback bind prints the "
                                 "privacy warning and proceeds because you asked")
    portal_cmd.add_argument("--port", type=int, default=8788)
    portal_cmd.add_argument("--allow-host", action="append", default=[], metavar="NAME[:PORT]",
                            help="an extra Host/Origin authority to answer for, e.g. the name a "
                                 "reverse proxy in front forwards; repeatable. Loopback names on "
                                 "the bound port are always allowed")
    portal_cmd.set_defaults(func=_portal)

    api_cmd = sub.add_parser("api", help="the read-only JSON API the portal frontend fetches")
    api_cmd.add_argument("--projects-dir", default="projects",
                         help="every project under this directory is served")
    api_cmd.add_argument("--store", default="store", help="where generated data lives")
    api_cmd.add_argument("--host", default="127.0.0.1",
                         help="loopback only by default; a non-loopback bind prints the "
                              "privacy warning and proceeds because you asked")
    api_cmd.add_argument("--port", type=int, default=8788)
    api_cmd.add_argument("--allow-host", action="append", default=[], metavar="NAME[:PORT]",
                         help="an extra Host/Origin authority to answer for, e.g. the name a "
                              "reverse proxy in front forwards; repeatable. Loopback names on "
                              "the bound port are always allowed")
    api_cmd.set_defaults(func=_api)

    control_cmd = sub.add_parser(
        "control", help="the authenticated write boundary the portal posts to")
    control_cmd.add_argument("--projects", default="projects",
                             help="every project under this directory is served")
    control_cmd.add_argument("--store", default="store", help="where generated data lives")
    control_cmd.add_argument("--bind", default="127.0.0.1",
                             help="loopback only; a non-loopback bind is refused unless "
                                  "--allow-host names the authority of the proxy in front")
    control_cmd.add_argument("--port", type=int, default=8790)
    control_cmd.add_argument("--allow-host", action="append", default=[],
                             metavar="NAME[:PORT]",
                             help="an extra Host/Origin authority to answer for, e.g. the "
                                  "name a reverse proxy in front forwards; repeatable. "
                                  "Naming one authorizes the non-loopback bind it fronts")
    control_cmd.add_argument("--state-dir", default=None,
                             help="operator accounts and markers; default $CLAIMSTONE_STATE_DIR "
                                  "or .claimstone/")
    control_cmd.add_argument("--credentials-file", default=None, metavar="PATH|none",
                             help="the .env credential writes go to (default: beside the "
                                  "projects directory); `none` turns credential writes off")
    control_cmd.set_defaults(func=_control)

    operator_cmd = sub.add_parser("operator", help="who may hold a control-API session")
    operator_sub = operator_cmd.add_subparsers(dest="operator_command", required=True)
    operator_add = operator_sub.add_parser(
        "add", help="record an operator; prompts for the password twice")
    operator_add.add_argument("id", help="the id a session authenticates")
    operator_add.add_argument("--name", required=True,
                              help="display name, recorded with the row and shown when signed")
    operator_disable = operator_sub.add_parser(
        "disable", help="append a disabling row; the id can no longer log in")
    operator_disable.add_argument("id", help="the operator id to disable")
    operator_cmd.set_defaults(func=_operator)

    export_cmd = sub.add_parser("export", help="freeze one flow's ledgers into a verifiable snapshot")
    export_cmd.add_argument("project", help="path to a project directory")
    export_cmd.add_argument("flow_id", help="the 64-hex flow id to export")
    export_cmd.add_argument("--store", default="store", help="where generated data lives")
    export_cmd.set_defaults(func=_export)

    export_verify = sub.add_parser("export-verify",
                                   help="check an export against the live ledgers and project")
    export_verify.add_argument("dir", help="the export directory (its manifest.json)")
    export_verify.add_argument("--projects-dir", default="projects",
                               help="where the project lives; needed to recompute outputs")
    export_verify.set_defaults(func=_export_verify)

    for name, handler, help_text in (
        ("model-run", _model_run, "drain a lane's queue on a named backend"),
        ("model-report", _model_report, "what a queue cost and how fast it went"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("project", help="path to a project directory")
        command.add_argument("lane", help="extract or review")
        command.add_argument("--batch", required=True, help="which batch to work on")
        command.add_argument("--store", default="store", help="where generated data lives")
        command.set_defaults(func=handler)
        if name == "model-run":
            # Required: which backend serves a lane is a finding, not a default (D13).
            command.add_argument("--backend", required=True,
                                 help="one of " + ", ".join(BACKENDS))
            command.add_argument("--model", help="model id for backends that need one")
            command.add_argument("--limit", type=int, default=None)
            command.add_argument("--retry-class", action="append",
                                 help="re-open a terminal class by name, e.g. TRUNCATED. The "
                                      "named-campaign rule: deliberate, and for a stated reason")
            group = command.add_mutually_exclusive_group()
            group.add_argument("--think", dest="think", action="store_true", default=None,
                               help="ask the backend to reason before answering")
            group.add_argument("--no-think", dest="think", action="store_false",
                               help="forbid it: on this lane reasoning spends the answer's budget")
            command.add_argument("--enforce-schema", action="store_true",
                                 help="send the request's schema to the backend so the shape is imposed "
                                      "rather than asked for; not every backend accepts it")
            command.add_argument("--rejudge", action="store_true",
                                 help="re-read stored answers under the current rules; no call")
        if name == "model-report":
            command.add_argument("--json", action="store_true")

    for stage in STAGES:
        placeholder = sub.add_parser(stage, help=f"(not implemented) stage: {stage}")
        placeholder.set_defaults(func=_not_implemented, stage_name=stage)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # A CLI stage makes read/modify/write decisions across several ledgers.
        # Hold the same project lock used by flow, source selection and Store.append.
        # The scheduler uses finer unit boundaries; the legacy CLI remains safely
        # serialized even when two terminals start the same stage concurrently.
        writers = {"import-manifest", "acquire", "discover", "regate", "normalize",
                   "extract", "review", "synthesize", "adjudicate", "model-run"}
        writes = args.command in writers or (args.command == "flow" and
                                              args.flow_command in {"create", "title"})
        if args.command == "acquire" and args.dry_run:
            writes = False
        if args.command == "normalize" and args.confirm_audit:
            writes = False
        if args.command == "flow" and not writes:
            return int(args.func(args))
        if writes:
            from claimstone.store import Store
            from pathlib import Path

            with Store(Path(args.project).name, base=args.store).writer_lock():
                return int(args.func(args))
        return int(args.func(args))
    except ConfigError as exc:
        # A contract violation is the user's to fix, so it gets a sentence rather than a
        # traceback. `validate` handles its own and never reaches here.
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
