"""The figure that gates verdicts, and the collapse that keeps it honest."""

from claimstone import admissibility
from claimstone.config import load_project
from claimstone.store import Store


def _ledger(store, rows):
    """Append acquisition rows, registering each key as a found candidate first.

    A source cannot be acquired without having been found. The old helper appended only
    acquisitions, which is exactly the assumption the denominator fix removes.
    """
    seen: set[str] = set()
    for row in rows:
        key = str(row["candidate_key"])
        if key not in seen:
            seen.add(key)
            store.append("candidates.jsonl",
                         {"candidate_key": key, "source_id": key,
                          "source_class": row.get("source_class"), "url": row.get("url")})
        store.append("acquisitions.jsonl", row)


def row(key, *, acquired, klass="ACA", failure=None, url="https://x.example/a"):
    return {"candidate_key": key, "source_class": klass, "acquired": acquired,
            "failure_class": failure, "url": url, "fetched_at": "2026-09-22T10:00:00+00:00"}


def test_a_failed_retry_does_not_erase_a_recorded_success(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("a", acquired=False, failure="PAYWALL_403")])
    assert admissibility.rate(store)["obtained"] == 1


def test_the_rate_is_acquired_over_attempted(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("b", acquired=True),
                    row("c", acquired=False, failure="PAYWALL_403")])
    result = admissibility.rate(store)
    assert (result["found"], result["obtained"]) == (3, 2)
    assert round(result["rate"], 2) == 0.67


def test_classes_are_reported_separately(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True, klass="ACA"),
                    row("b", acquired=False, klass="DOC", failure="NOT_FOUND_404"),
                    row("c", acquired=False, klass="DOC", failure="PAYWALL_403")])
    by_class = admissibility.rate(store)["by_class"]
    assert {key: by_class["ACA"][key] for key in ("found", "obtained", "rate")} == {"found": 1, "obtained": 1, "rate": 1.0}
    assert by_class["DOC"]["rate"] == 0.0


def test_an_empty_ledger_has_no_rate_rather_than_a_rate_of_zero(tmp_path):
    store = Store("t", base=tmp_path)
    result = admissibility.rate(store)
    assert result["found"] == 0
    assert result["rate"] is None


def test_below_the_floor_the_round_produces_no_verdicts(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("b", acquired=False, failure="PAYWALL_403")])
    project = load_project("projects/example-news-and-returns")
    verdict = admissibility.admit(project, store)
    assert verdict["status"] == "INSUFFICIENT_ACQUISITION"
    assert verdict["floor"] == 0.80


def test_at_or_above_the_floor_the_round_is_admissible(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row(k, acquired=True) for k in "abcd"]
                   + [row("e", acquired=False, failure="PAYWALL_403")])
    project = load_project("projects/example-news-and-returns")
    assert admissibility.admit(project, store)["status"] == "OK"


def test_there_is_no_override(tmp_path):
    import inspect

    source = inspect.getsource(admissibility.admit)
    assert "force" not in source and "override" not in source


def test_a_regate_supersedes_a_success_but_a_retry_does_not(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [
        row("a", acquired=True),                                    # accepted without a gate
        {**row("a", acquired=False, failure="ABSTRACT_ONLY"),
         "regated_from": "2026-09-22T10:00:00+00:00"},               # corrected judgement
    ])
    assert admissibility.rate(store)["obtained"] == 0

    store2 = Store("u", base=tmp_path)
    _ledger(store2, [row("a", acquired=True),
                     row("a", acquired=False, failure="PAYWALL_403")])  # a retry, not a re-gate
    assert admissibility.rate(store2)["obtained"] == 1


def test_a_real_acquisition_after_a_regate_wins_again(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [
        row("a", acquired=True),
        {**row("a", acquired=False, failure="ABSTRACT_ONLY"),
         "regated_from": "2026-09-22T10:00:00+00:00"},
        row("a", acquired=True),   # the cascade found the real document later
    ])
    assert admissibility.rate(store)["obtained"] == 1


def test_a_row_without_a_class_is_filed_under_the_candidates_class(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "a", "source_class": "ACA"})
    store.append("acquisitions.jsonl", {"candidate_key": "a", "acquired": False,
                                        "failure_class": "PAYWALL_403",
                                        "url": "https://wall.example/a"})
    by_class = admissibility.rate(store)["by_class"]
    assert "UNCLASSIFIED" not in by_class
    assert by_class["ACA"]["found"] == 1


# --- the denominator: what the floor is a share of ----------------------------

def _found(store, n, *, klass="ACA"):
    """n candidates discovered. This is what the floor is a share of."""
    for index in range(n):
        store.append("candidates.jsonl", {"candidate_key": f"k{index}", "source_class": klass})


def test_the_denominator_is_what_was_found_not_what_was_attempted(tmp_path):
    # The defect this replaces: dividing by acquisition rows let one obtained source out of
    # twenty-five found report a rate of 1.00 and pass the floor — a corpus read at 4%
    # certifying itself complete, which is the failure this project exists to prevent.
    store = Store("t", base=tmp_path)
    _found(store, 25)
    _ledger(store, [row("k0", acquired=True)])
    result = admissibility.rate(store)
    assert result["found"] == 25
    assert result["attempted"] == 1
    assert result["obtained"] == 1
    assert result["rate"] == 1 / 25


def test_an_unread_corpus_does_not_pass_the_floor(tmp_path):
    store = Store("t", base=tmp_path)
    _found(store, 25)
    _ledger(store, [row("k0", acquired=True)])
    project = load_project("projects/example-news-and-returns")
    assert admissibility.admit(project, store)["status"] == "INSUFFICIENT_ACQUISITION"


def test_the_chain_of_states_is_reported_separately(tmp_path):
    store = Store("t", base=tmp_path)
    _found(store, 4)
    store.append("candidates.jsonl", {"candidate_key": "k4", "source_class": None})
    _ledger(store, [row("k0", acquired=True), row("k1", acquired=True),
                    row("k2", acquired=False, failure="PAYWALL_403")])
    result = admissibility.rate(store)
    assert (result["found"], result["classified"]) == (5, 4)
    assert (result["attempted"], result["obtained"]) == (3, 2)


def test_an_unclassified_candidate_stays_in_the_denominator(tmp_path):
    # It was found and it was not read. Dropping it into a smaller denominator is the same
    # inflation, arrived at from the other side.
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "k0", "source_class": "ACA"})
    store.append("candidates.jsonl", {"candidate_key": "k1", "source_class": None})
    _ledger(store, [row("k0", acquired=True)])
    result = admissibility.rate(store)
    assert result["found"] == 2
    assert result["rate"] == 0.5
    assert result["unclassified"] == 1


def test_an_acquisition_with_no_candidate_is_reported_not_absorbed(tmp_path):
    # Adding it to `found` would reintroduce the inflation; hiding it would hide a broken
    # ledger. It is counted on its own line.
    store = Store("t", base=tmp_path)
    _found(store, 2)
    store.append("acquisitions.jsonl", row("k0", acquired=True))
    store.append("acquisitions.jsonl", row("ghost", acquired=True))
    result = admissibility.rate(store)
    assert result["found"] == 2
    assert result["orphan_acquisitions"] == ["ghost"]


def test_no_candidates_means_no_rate_rather_than_zero(tmp_path):
    store = Store("t", base=tmp_path)
    result = admissibility.rate(store)
    assert result["found"] == 0
    assert result["rate"] is None


def test_a_round_can_be_isolated(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "k0", "source_class": "ACA",
                                      "round": "spring"})
    store.append("candidates.jsonl", {"candidate_key": "k1", "source_class": "ACA",
                                      "round": "autumn"})
    store.append("acquisitions.jsonl", row("k0", acquired=True))
    assert admissibility.rate(store, round_name="spring")["found"] == 1
    assert admissibility.rate(store, round_name="spring")["rate"] == 1.0
    assert admissibility.rate(store, round_name="autumn")["rate"] == 0.0


# --- what is unknown stays unknown --------------------------------------------

def test_an_unnormalized_source_raises_the_ceiling_not_the_figure(tmp_path):
    # Replaces three tests that asserted the opposite. They encoded a design a review broke: the
    # obtained rate carried the headline while normalization ran, so a source already known not to
    # be a document was ignored because stage 3 had not reached the others.
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("b", acquired=True)])
    store.append("documents.jsonl", {"source_id": "a", "fulltext_confirmed": True})
    result = admissibility.rate(store)
    assert result["confirmed"] == 1
    assert result["awaiting_normalize"] == 1
    assert result["rate"] == 0.5          # established
    assert result["rate_upper"] == 1.0    # still possible
    assert result["final"] is False


def test_a_refuted_source_lowers_both_bounds(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row("a", acquired=True), row("b", acquired=True)])
    store.append("documents.jsonl", {"source_id": "a", "fulltext_confirmed": True})
    store.append("documents.jsonl", {"source_id": "b", "fulltext_confirmed": False,
                                     "failure_class": "NOT_A_DOCUMENT"})
    result = admissibility.rate(store)
    assert result["rate"] == result["rate_upper"] == 0.5
    assert result["final"] is True


# --- the denominator: what the floor is a share of ----------------------------

def _found(store, n, *, klass="ACA"):
    """n candidates discovered. This is what the floor is a share of."""
    for index in range(n):
        store.append("candidates.jsonl", {"candidate_key": f"k{index}", "source_class": klass})


def test_the_denominator_is_what_was_found_not_what_was_attempted(tmp_path):
    # The defect this replaces: dividing by acquisition rows let one obtained source out of
    # twenty-five found report a rate of 1.00 and pass the floor — a corpus read at 4%
    # certifying itself complete, which is the failure this project exists to prevent.
    store = Store("t", base=tmp_path)
    _found(store, 25)
    _ledger(store, [row("k0", acquired=True)])
    result = admissibility.rate(store)
    assert result["found"] == 25
    assert result["attempted"] == 1
    assert result["obtained"] == 1
    assert result["rate"] == 1 / 25


def test_an_unread_corpus_does_not_pass_the_floor(tmp_path):
    store = Store("t", base=tmp_path)
    _found(store, 25)
    _ledger(store, [row("k0", acquired=True)])
    project = load_project("projects/example-news-and-returns")
    assert admissibility.admit(project, store)["status"] == "INSUFFICIENT_ACQUISITION"


def test_the_chain_of_states_is_reported_separately(tmp_path):
    store = Store("t", base=tmp_path)
    _found(store, 4)
    store.append("candidates.jsonl", {"candidate_key": "k4", "source_class": None})
    _ledger(store, [row("k0", acquired=True), row("k1", acquired=True),
                    row("k2", acquired=False, failure="PAYWALL_403")])
    result = admissibility.rate(store)
    assert (result["found"], result["classified"]) == (5, 4)
    assert (result["attempted"], result["obtained"]) == (3, 2)


def test_an_unclassified_candidate_stays_in_the_denominator(tmp_path):
    # It was found and it was not read. Dropping it into a smaller denominator is the same
    # inflation, arrived at from the other side.
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "k0", "source_class": "ACA"})
    store.append("candidates.jsonl", {"candidate_key": "k1", "source_class": None})
    _ledger(store, [row("k0", acquired=True)])
    result = admissibility.rate(store)
    assert result["found"] == 2
    assert result["rate"] == 0.5
    assert result["unclassified"] == 1


def test_an_acquisition_with_no_candidate_is_reported_not_absorbed(tmp_path):
    # Adding it to `found` would reintroduce the inflation; hiding it would hide a broken
    # ledger. It is counted on its own line.
    store = Store("t", base=tmp_path)
    _found(store, 2)
    store.append("acquisitions.jsonl", row("k0", acquired=True))
    store.append("acquisitions.jsonl", row("ghost", acquired=True))
    result = admissibility.rate(store)
    assert result["found"] == 2
    assert result["orphan_acquisitions"] == ["ghost"]


def test_no_candidates_means_no_rate_rather_than_zero(tmp_path):
    store = Store("t", base=tmp_path)
    result = admissibility.rate(store)
    assert result["found"] == 0
    assert result["rate"] is None


def test_a_round_can_be_isolated(tmp_path):
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "k0", "source_class": "ACA",
                                      "round": "spring"})
    store.append("candidates.jsonl", {"candidate_key": "k1", "source_class": "ACA",
                                      "round": "autumn"})
    store.append("acquisitions.jsonl", row("k0", acquired=True))
    assert admissibility.rate(store, round_name="spring")["found"] == 1
    assert admissibility.rate(store, round_name="spring")["rate"] == 1.0
    assert admissibility.rate(store, round_name="autumn")["rate"] == 0.0


# --- the confirmed basis only when stage 3 has finished -----------------------




# --- admission must never be inflated by work not yet done ---------------------

def test_a_known_negative_counts_against_even_while_normalize_runs(tmp_path):
    # The first fix made the confirmed basis wait for completeness, and the obtained basis then
    # ignored the confirmations already in hand: four obtained, one already known not to be a
    # document, three awaiting — and it returned OK at 1.00.
    store = Store("t", base=tmp_path)
    _ledger(store, [row(k, acquired=True) for k in "abcd"])
    store.append("documents.jsonl", {"source_id": "a", "fulltext_confirmed": False,
                                     "failure_class": "NOT_A_DOCUMENT"})
    project = load_project("projects/example-news-and-returns")
    verdict = admissibility.admit(project, store)
    assert verdict["status"] == "INSUFFICIENT_ACQUISITION"
    assert verdict["rate"] == 0.0
    assert verdict["rate_upper"] == 0.75


def test_the_rate_is_the_lower_bound_and_the_upper_is_reported(tmp_path):
    # What is unknown stays unknown. Admission gates on what is established; the ceiling says
    # how much better it could still turn out to be.
    store = Store("t", base=tmp_path)
    _ledger(store, [row(k, acquired=True) for k in "abcd"])
    store.append("documents.jsonl", {"source_id": "a", "fulltext_confirmed": True})
    result = admissibility.rate(store)
    assert result["rate"] == 0.25
    assert result["rate_upper"] == 1.0
    assert result["final"] is False


def test_admission_is_final_only_when_nothing_is_outstanding(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row(k, acquired=True) for k in "abcde"])
    for key in "abcd":
        store.append("documents.jsonl", {"source_id": key, "fulltext_confirmed": True})
    store.append("documents.jsonl", {"source_id": "e", "fulltext_confirmed": False,
                                     "failure_class": "NOT_A_DOCUMENT"})
    verdict = admissibility.admit(load_project("projects/example-news-and-returns"), store)
    assert verdict["final"] is True
    assert verdict["rate"] == verdict["rate_upper"] == 0.8
    assert verdict["status"] == "OK"


def test_an_orphan_acquisition_blocks_a_final_admission(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row(k, acquired=True) for k in "abcd"])
    store.append("acquisitions.jsonl", row("ghost", acquired=True))
    for key in "abcd":
        store.append("documents.jsonl", {"source_id": key, "fulltext_confirmed": True})
    verdict = admissibility.admit(load_project("projects/example-news-and-returns"), store)
    assert verdict["final"] is False
    assert verdict["blocking"] == ["orphan_acquisitions"]


def test_a_repaired_ledger_blocks_a_final_admission(tmp_path):
    # A repair means rows were lost. Whatever they were, the round is not complete until someone
    # has reconciled what went missing.
    store = Store("t", base=tmp_path)
    _ledger(store, [row(k, acquired=True) for k in "abcd"])
    for key in "abcd":
        store.append("documents.jsonl", {"source_id": key, "fulltext_confirmed": True})
    store.append("ledger_repairs.jsonl", {"ledger": "acquisitions.jsonl", "discarded_bytes": 40})
    verdict = admissibility.admit(load_project("projects/example-news-and-returns"), store)
    assert verdict["final"] is False
    assert "ledger_repairs" in verdict["blocking"]


def test_before_normalize_runs_nothing_is_final(tmp_path):
    store = Store("t", base=tmp_path)
    _ledger(store, [row(k, acquired=True) for k in "abcde"])
    verdict = admissibility.admit(load_project("projects/example-news-and-returns"), store)
    assert verdict["final"] is False
    assert "normalize_not_started" in verdict["blocking"]


def test_a_round_can_be_isolated_so_two_populations_are_not_one_figure(tmp_path):
    """A discovery round changes the denominator by design, which is why the floor is per round.

    Reproduced on the real store: running the citation channel against alembic-s4 took the settled
    figure from 14/25 = 0.56 to 14/75 = 0.19 — correct for the whole store and meaningless as a
    comparison, because 50 of those 75 are references admitted by a rule that deliberately favours
    canonical works, many of which have no open copy at all.
    """
    store = Store("t", base=tmp_path)
    for n in range(2):
        key = f"doi:10.1/manifest{n}"
        store.append("candidates.jsonl", {"candidate_key": key, "source_class": "ACA",
                                          "round": "manifest", "channel": "keyword"})
        store.append("acquisitions.jsonl", {"candidate_key": key, "source_id": f"M{n}",
                                            "acquired": True, "sha256": f"h{n}",
                                            "source_class": "ACA"})
        store.append("documents.jsonl", {"source_id": f"M{n}", "sha256": f"h{n}",
                                         "fulltext_confirmed": True})
    for n in range(8):
        store.append("candidates.jsonl", {"candidate_key": f"title:a cited work {n}",
                                          "source_class": None, "round": "citations",
                                          "channel": "citation"})

    whole = admissibility.rate(store)
    assert (whole["found"], whole["confirmed"]) == (10, 2)

    manifest = admissibility.rate(store, round_name="manifest")
    assert (manifest["found"], manifest["confirmed"]) == (2, 2)
    assert manifest["rate"] == 1.0
    assert manifest["final"] is True

    citations = admissibility.rate(store, round_name="citations")
    assert citations["found"] == 8
    assert citations["classified"] == 0


def test_the_manifest_is_a_population_the_floor_can_be_judged_over(tmp_path):
    """A curated reading list is what `sources.yaml`'s floor was written about, and a round is not always
    the right selector for it. The pilot corpus discovered 199 candidates and *then* curated 28 of them, so
    every one of the 28 carries the round that first found it — correctly, since discovery found them — and
    judging the floor over that round would divide by 199.

    A manifest row declares itself with a `source_id`; a discovered one has none. That is the population.
    """
    store = Store("t", base=tmp_path)
    for n in range(2):
        key = f"doi:10.1/declared{n}"
        store.append("candidates.jsonl", {"candidate_key": key, "source_class": "ACA",
                                          "source_id": f"ACA{n:03d}", "round": "sweep"})
        store.append("acquisitions.jsonl", {"candidate_key": key, "source_id": f"ACA{n:03d}",
                                            "acquired": True, "sha256": f"h{n}", "source_class": "ACA"})
        store.append("documents.jsonl", {"source_id": f"ACA{n:03d}", "sha256": f"h{n}",
                                         "fulltext_confirmed": True})
    for n in range(8):
        store.append("candidates.jsonl", {"candidate_key": f"doi:10.9/found{n}", "source_class": "ACA",
                                         "round": "sweep"})

    whole = admissibility.rate(store)
    assert (whole["found"], whole["confirmed"]) == (10, 2)

    declared = admissibility.rate(store, manifest_only=True)
    assert (declared["found"], declared["confirmed"]) == (2, 2)
    assert declared["rate"] == 1.0
    assert declared["final"] is True


def test_a_filtered_population_reports_no_orphans(tmp_path):
    """An acquisition row outside a filtered population belongs to a candidate the filter excluded. Calling
    it an orphan said "the ledger is inconsistent" about a ledger that was fine."""
    store = Store("t", base=tmp_path)
    store.append("candidates.jsonl", {"candidate_key": "doi:10.1/declared", "source_class": "ACA",
                                      "source_id": "ACA001", "round": "sweep"})
    store.append("candidates.jsonl", {"candidate_key": "doi:10.9/found", "source_class": "ACA",
                                      "round": "sweep"})
    store.append("acquisitions.jsonl", {"candidate_key": "doi:10.9/found", "acquired": False,
                                        "failure_class": "PAYWALL_403", "source_class": "ACA"})
    assert admissibility.rate(store, manifest_only=True)["orphan_acquisitions"] == []
    assert admissibility.rate(store)["orphan_acquisitions"] == []
