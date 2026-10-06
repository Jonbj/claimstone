# Research portal: implementation review

**Status:** adversarial review of the P0–P2b implementation produced from
`2026-10-06-research-portal-opencode-prompt.md`, run from
`2026-10-06-research-portal-implementation-review-prompt.md`. The operator then asked for the
necessary corrections, so this review **also applies its fixes**. Each finding says whether it was
fixed, and every fix has a regression test (R1–R10).
**Date:** 2026-10-06.

Labels: **[CODE]** verified by reading the cited code. **[RUN]** verified by running the named
command. **[INFER]** a design inference. **[UNRESOLVED]** depends on something not visible here.

Nothing under `projects/` was modified. Nothing under `store/` was written: a `find store -newer
<file>` check after every live run returned nothing. Live-store contact was limited to:

- read-only GETs against a loopback portal;
- one read-only `cProfile` run;
- one `export` / `export-verify` round trip on a scratch **copy** of `store/pmc-screen-time`
  (`raw/`, `tei/` and `audits/` excluded).

---

## 1. Findings by severity

### High

**I1. The only profile awaiting a person was invisible in the portal.** [RUN] [CODE] — **fixed**

`store/pmc-screen-time/profiles.jsonl` holds 16 rows, all with `round: null`:

- 8 legacy rows without `profile_version`;
- 8 rows with `profile_version 5`.

The command was a read-only count. These include Q04, which `HANDOFF.md` says is ready for human
reading. `flows.legacy_selectors` (`flows.py:170-175`) lists candidate rounds only, and no route
named the whole-store selector. So `/p/pmc-screen-time/legacy/pmc-oa-v1/` rendered no profiles and
no adjudication card.

Fix:
- `portal_state.unbound_selectors` adds the whole-store selector and every `(round,
  manifest_only)` pair under which a profile or an adjudication exists.
- `/p/<p>/legacy/-/` is the whole store; a `~manifest` suffix selects `manifest_only`.
- The slug is looked up, never invented (I6).

Verified after the fix: the whole-store page shows `Q04 — no verdict recorded` with `--profile-sha256
9340389c9aac29b77e901c20e27434d211fe9e7825a68d99995d8c6fa5b20fdd`, the hash in `HANDOFF.md`.

**I2. A flow page recomputed everything three to five times.** [RUN] — **fixed**

`cProfile` of `portal_state.flow_overview` on `pmc-screen-time` measured 52.7 s under the profiler.
In that run:

| function | calls |
|---|---|
| `synthesize.verdicts` | 5 |
| `round_state.state` | 3 |
| `claim_records.current` | 16 |

`flow_overview`, `question_matrix` and `inbox_cards` each recomputed state independently. D82
attributed the 15.43 s page time to "re-read from disk on every request", which was not the cause.

Fix:
- `portal_state.compute()` produces one `Computed` per selector per request, shared by every panel.
- `round_state.state(..., precomputed_verdicts=)` accepts the request's own result.

This is not a cache: nothing outlives the request. The flow page went from 15.24 s to **3.89–4.05 s**
[RUN]. Test R2 asserts one `verdicts` and one `state` call per flow page.

**I3. The adjudication card proposed a signature the engine would refuse.** [CODE] — **fixed**

`synthesize.adjudicate` raises `StaleProfile` when the stored profile differs from current
evidence (`synthesize.py:200-203`). The card nevertheless printed `adjudicate ... --profile-sha256
<live hash>` even when `stored_profile_stale` was true.

Test I-T5 passed only because its fixture wrote stored profiles with invented hashes
(`sha256_text("stored-Q..")`). Its rows therefore *always* differed from the live profile, so the
test proved a command `adjudicate` cannot accept.

Fix:
- On a stale stored profile the card shows `claimstone synthesize ...` and says why.
- The fixture now builds profiles with the real `synthesize.build`.
- I-T5 checks that the hash on the card is the stored one, and a new test covers the stale case.

### Medium

**I4. The index and `/inbox` compute every selector of every project.** [RUN] — **not fixed;
recorded in D82**

After I1 and I2, the real store takes **28.9 s** for `/` and **29.1 s** for `/inbox`. The remedy is
architectural: per-project and per-selector API calls that the page loads lazily. See the frontend
design.

**I5. Export identity ignored instruments and the live protocol.** [CODE] — **fixed**

`export_id` hashed `flow_id`, `selector` and `prefixes` only (`export.py`). After a gate or floor
change, a re-export over unchanged bytes answered `exists` with outputs the current code no longer
produces. Verify would then fail on an export the operator had just been told exists.

The id now includes `export_version`, `instrument_versions` and the live `protocol_sha256` and
`registry_sha256`, and the manifest records the latter two. Test: R10.

**I6. The legacy route accepted any round name.** [CODE] — **fixed**

`/p/<p>/legacy/<anything>/` built `Selector(<anything>)` and rendered an empty round, which reads as
"this round found nothing". It is now a lookup among existing selectors, and anything else is a 404.
Test: R8.

**I7. `/inbox` silently dropped a project whose configuration fails.** [CODE] — **fixed**

`_inbox_data` did `except ConfigError: continue`, so the project needing a person disappeared from
the queue. It is now an INTEGRITY card with `claimstone validate <path>`. Test: R9.

**I8. A forged or hand-edited flow row kept its trusted id.** [CODE] — **fixed**

`flows.flows()` accepted any `created` row and never checked `flow_id == sha256(binding)`. Such rows
are now excluded and listed by `flows.invalid_flows`, and shown on the integrity panel. Test: R4.

**I9. The instrument check crashed inside the container image.** [CODE] [INFER] — **fixed**

`_load_instrument_checker` resolved `tools/` next to the installed package. In the image the
package sits in site-packages, so the integrity and admin pages would have raised a 500.

The checker is now looked up in the checkout, then `$CLAIMSTONE_ROOT`, then the working directory.
When it is absent the result is the named problem `UNAVAILABLE`, never an empty (passing) list.
Test: R5.

**I10. Acquisition cards offered an unpreviewed sweep, and `--retry-class UNCLASSIFIED`.**
[CODE] — **fixed**

AGENTS.md requires asking before a sweep of any size. Routine cards now end in `--dry-run` and carry
the authorization note. `UNCLASSIFIED` is a refusal before any request, so it gets only the
CLASSIFICATION card. Test: R3.

**I11. The flows table on the project page always said "(whole store)".** [CODE] — **fixed**

The table read `row["selector"]`, which does not exist on a `created` row (the field is
`binding.selector`). Flow links were also missing from the index and the project page. Both now
link and label correctly.

### Low

**I12. Host and Origin checks.** [CODE] — **fixed**
- `[::1]:<other port>` passed, because the port check skipped bracketed hosts.
- The Origin port was never compared.
- A wildcard bind (`0.0.0.0`) was added to the allowlist as if it were a name.

`--allow-host NAME[:PORT]` is new and is required behind a reverse proxy. Tests: R6, R7.

**I13. A-T1 asserted the wrong secret length.** [CODE] — **fixed**

`secret-value-123` is 16 characters, and the test asserted `"15"` absent. The error was in my own
implementation spec (§4.13) and the test inherited it. The test now checks that the credentials
block holds booleans only.

**I14. HANDOFF overstated F1.** [CODE] — **fixed**

It said "confirmations no longer leak across rounds". Admission still reads confirmations and
repairs project-wide, as D82 correctly states.

**I15. Leftovers.** [CODE] — **not fixed** (cosmetic):
- `round_state._profiles_for_spine` is dead code; it was already dead before this work.
- `portal._poll_script` HTML-escapes a value inside JS; that is safe for directory names but
  semantically wrong.

### Invariants checked against the new code

| check | result |
|---|---|
| No route writes | **Holds** [RUN] [CODE]. Only GET is routed; `do_POST/PUT/DELETE/PATCH/HEAD/OPTIONS` and `__getattr__` all lead to `_refuse`; the 500 path writes only the response. H-T6 hashes the tmp store before and after 17 routes. On the real store, `find store -newer` found nothing after every portal run. |
| No verdict signed or prefilled | **Holds**. Placeholders stay literal (I-T5); the card's verdict is never one of the five. |
| `AI_PROVISIONAL` advisory only | **Holds**. ADVISORY cards carry no command. |
| Per-class counts before pooled | **Holds** in the matrix (`claims_by_class` then total) and in the export CSV. |
| Verdict vocabulary | **Holds**. `NO_VERIFIED_CLAIM` renders dashed with its own word; operational questions show `LITERATURE_VERDICT_NOT_APPLICABLE`. |

## 2. Conformance table

| spec id | test | verdict |
|---|---|---|
| T1 | `test_candidate_predicate_matches_admissibility` | proves it |
| T2 | `test_round_state_claims_do_not_leak_between_rounds` | proves it |
| T3 | `test_round_state_review_and_chunks_scoped` | proves it |
| T4 | `test_scoped_activity_and_last_write_exclude_other_round` | proves it |
| T5 | `test_whole_store_state_unchanged` | **proves less**: it asserts this fixture's concrete numbers, not equality with the pre-change code. Acceptable, since the pre-existing round_state tests also pass unchanged. |
| T6 | `test_profile_population_refactor_is_identical` | proves it (compares against the old body inline) |
| T7 | `test_corrupt_acquisitions_is_an_error_not_zero` | proves it |
| T8 | `test_round_less_candidate_is_not_routine` | proves it |
| T9 | `test_dashboard_renders_integrity_section` (in `test_dashboard.py`) | proves it |
| F-T1…F-T8 | `tests/test_flows.py` | prove it; F-T8 hashes the store before and after |
| P-T1 | `test_index_lists_flows_and_legacy_selectors` | proves it; the whole-store gap (I1) was outside the spec row |
| P-T2 | `test_flow_overview_leaks_no_other_round` | proves it (`S03`, `r2-a`, `r2-w` absent from the JSON) |
| P-T3 | `test_protocol_drift_banner_and_live_floor` | proves it |
| I-T1, I-T2 | as named | prove it |
| I-T3 | `test_work_cards_signature_and_stance_independence` | proves it; the signature pin is the strong part, and stance flipping is a second check on the same builder |
| I-T4 | `test_every_command_parses_with_the_real_parser` | proves it (now also covers `--dry-run` and `synthesize`) |
| I-T5 | `test_adjudication_card_carries_hash_and_placeholder` | **proved less → fixed** (I3) |
| L-T1, L-T2 | as named | prove it |
| A-T1 | `test_admin_state_never_leaks_values` | **proved less → fixed** (I13) |
| G-T1 | `test_integrity_names_corruption_and_touches_nothing` | proves it |
| F-T9 | `test_floor_panel_needed_arithmetic` | proves it |
| H-T1…H-T5 | `tests/test_portal.py` | prove it; H-T5 needed a registry bump once profiles were built for real (invariant 5) |
| H-T6 | `test_serving_every_route_writes_nothing` | proves it for the 17 success routes; error routes are not exercised, but have no write path [CODE] |
| E-T1…E-T7 | `tests/test_export.py` | prove it; E-T3 flips byte 10 of `candidates.jsonl`, inside the recorded prefix |

## 3. Decisions and deviations in the progress log

| decision / deviation | verdict |
|---|---|
| T9 lives in `test_dashboard.py` | endorse |
| `errors` de-duplicated in first-seen order | endorse |
| `flow title --by` defaults to `getpass.getuser()` | endorse. It is display metadata, not a signature. |
| `flow check` reports `RegistryDrift` as exit 4 | endorse |
| bound-after-data warning on stdout | endorse |
| F-T3 marker without `EDITED:` | endorse |
| `work_cards` with empty scope, filled by the caller | endorse. It keeps the pinned signature. |
| `bind_port` set after bind for port 0 | endorse |
| integrity computes code identity when not handed it | endorse |
| dashboard helpers imported, not copied | endorse |
| **Deviation:** `adjudicate` takes the question positionally | endorse. The spec was wrong, and `build_parser` decides. |
| `exports.jsonl` excluded from the snapshot | endorse. The reasoning is right, and E-T5 needs it. |
| `export-verify --projects-dir` | endorse |
| two parser-version CSV columns | endorse |
| D82 written at P2, not last | endorse (the instrument check requires it) |
| *Implicit:* the page-time explanation in D82 | **reject**. It was misattributed (I2), and the D82 text is corrected. |
| *Implicit:* legacy = candidate rounds only | **reject**. It followed the spec literally and hid Q04 (I1). The spec should have asked for every selector holding data. |

## 4. Command output, as run by this review

Before the fixes:
```
.venv/bin/pytest -q                              → 1180 passed, 7 skipped in 22.44s
.venv/bin/claimstone validate --all-projects     → exit 0 (six projects OK)
.venv/bin/python tools/check_instrument_versions.py → 26 instrument version(s) acknowledged in the design record
```

After the fixes:
```
.venv/bin/pytest -q                              → 1191 passed, 7 skipped in 27.15s
.venv/bin/claimstone validate --all-projects     → exit 0
.venv/bin/python tools/check_instrument_versions.py → 26 instrument version(s) acknowledged in the design record
```

Page times (`curl -s -o /dev/null -w '%{time_total}'`, loopback, real store, read-only):

| route | before | after |
|---|---|---|
| `/p/pmc-screen-time/legacy/pmc-oa-v1/` | 15.24 s (GLM measured 15.43 s) | 4.05 s, 3.89 s |
| `/p/pmc-screen-time/legacy/-/` | did not exist | 3.74 s |
| `/` | 19.31 s | 28.89 s (more selectors now listed, I1) |
| `/inbox` | — | 29.06 s |

Export round trip on a scratch copy of `pmc-screen-time` (flow on `pmc-oa-v1`): export 10.5 s, then
`export-verify` returned `verified: prefixes unchanged and outputs recompute identically`, exit 0.
`profiles.json` equalled the live `verdicts` result. **[RUN]** The round-scoped export holds zero
profile rows, because all profiles are whole-store (I1). That is correct, and it is the reason a
whole-store flow is the one to export for Q04.

## 5. What is safe to keep, and what must change before P3

**Safe to keep:**
- `scope.py`;
- the round_state scoping and error handling;
- `flows.py` (with I8);
- the export prefix and verify design (with I5);
- the transport's read-only structure.

The seven invariants hold in the new code.

**Before P3:**
1. Lazy, per-selector loading for the index and inbox (I4). The planned frontend/API split is the
   natural place for it.
2. Bind a whole-store flow for `pmc-screen-time` if Q04's evidence is to be exported. That is the
   operator's call: `claimstone flow create projects/pmc-screen-time --title ...` without `--round`.
3. Every P3 prerequisite already listed in the design review still stands: F5, F6, F7, F14, F15 and
   F16.
