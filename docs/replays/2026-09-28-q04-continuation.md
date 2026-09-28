# Q04 bounded continuation — prepared, blocked before reaching the service

Measured 2026-09-28. The operator delegated choosing models from Ollama's cloud catalogue and
authorised completing missing extraction and independent review before rebuilding Q04.

Extraction remains `ollama-cloud/deepseek-v4.1-flash`, reasoning off, schema requested.
Independent review uses `ollama-cloud/mistral-large-3:675b`, schema requested, no thinking flag.
Its JSON support is documented by [Ollama](https://ollama.com/library/mistral-large-3);
reviewer quality is not yet measured. These are task-local choices, not engine defaults.
API names were checked against [the cloud model catalogue](https://ollama.com/api/tags).

All ten missing effect responses were inspected: seven `NOT_JSON` stopped below the cap;
three `TRUNCATED` consumed all 2,500 output tokens. The recovery batch preserves current prompts
and schemas, raising the output cap to 7,500 and changing `call_id` honestly. This is a retry
hypothesis, not a predicted recovery. The full-result v2 review batch has 42 calls and 319,562
prompt characters, with 400 output tokens per call. New extraction may add review work.

## Recorded execution

One physical extraction attempt returned `BACKEND_ERROR` after DNS resolution of `ollama.com`
failed in the restricted agent environment. It has no usage, priced cost or response bytes.
No new annotation, review or rebuilt profile exists from this continuation. Q04 still reports
`awaiting_extract` and `awaiting_review`. A failed attempt is not a reading; unknown cost is not zero.

The local plan is `store/pmc-screen-time/audits/q04-run-plan.json`, SHA-256
`67d3cef369055d246b80803891503440fce97ae57457c2ea79acc3bc782ad848`.
The current audit is
`store/pmc-screen-time/audits/question-round/baf3b18896070d243a90b9d60ece38697da93e65dd370c8e98d4f2dd21695799.json`.
It explicitly corrects the manually entered timestamp of an earlier audit, which is retained;
measurements are unchanged. Raw passages and private project inputs remain gitignored.

## Continue on the host

```bash
.venv/bin/python tools/complete_question_round.py --plan store/pmc-screen-time/audits/q04-run-plan.json
.venv/bin/python tools/complete_question_round.py --plan store/pmc-screen-time/audits/q04-run-plan.json --execute
```

The first command only inspects. The second resumes extraction, harvests under the current gate,
adds independent full-annotation reviews, harvests review and rebuilds profiles only if Q04 is
complete. It stops at the first failure or budget boundary and records an audit. Existing successful
calls are skipped on resume. It never signs or adjudicates.

The cumulative ceiling is **USD 1**. Dated rates live in the plan: DeepSeek input/cached/output
0.30/0.006/1.20 and Mistral input/output 0.50/1.50 USD per million tokens, checked against
[Ollama pricing](https://ollama.com/pricing). Peak rates conservatively bound off-peak billing.
Each next call reserves its full declared context ceiling plus its output cap before contact;
input ceilings of 1,100,000 and 262,144 conservatively exceed the advertised 1M and 256K windows.
Physical attempts with unknown usage retain their reservation. The recorded DNS failure therefore
reserves **USD 0.339**, rather than claiming an actual charge or free execution. Reported usage is
accounted at plan rates; replay rows never add cost.

Five operational tests verify pre-call budget refusal, cumulative unknown-cost reservation and
one-failure stopping, own-reader refusal before payment, cached extraction adding complete reviews
without repeated calls or adjudication, and reading only two `.env` keys without executing shell
text. Required checks: 886 tests, 7 skipped; six valid projects; 16 instrument versions acknowledged.
No engine instrument, registry, floor or population changed.

## D51 follow-up: partial host run, harvested, strict format failure

The host resumed six extraction attempts: five valid answers, then one `NOT_JSON`. The failed
response is `[]` followed by a paragraph. It remains invalid in full; no suffix is discarded and
no model-produced absence is accepted by an operator's inference. Ollama's
[structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs) explicitly
states Cloud does not support structured outputs. `format=schema` records the requested shape,
not guaranteed enforcement. The runner comment that claimed enforcement has been corrected.

`claimstone extract projects/pmc-screen-time --batch q04-effect-recovery-2026-09-28 --harvest`
returns **20 accepted, zero rejected**, then **zero accepted/rejected and 20 already held** on repeat.
`tools/replay_answers.py projects/pmc-screen-time` now measures 1,688 scoped annotations, 259
rejections, 1,688 prospective full-review calls and 29 unanswered readings: effect 5, heterogeneity
4, method 15, premise 5. Q04 remains 42 annotations with five missing effect readings; harvest and
regate backlog are zero. No independent v2 review or new profile has been produced.

The plan extension is `store/pmc-screen-time/audits/q04-run-plan-v2.json`, SHA-256
`01a9183a2b2f53bf227b2599ca827bc96871b35f2b2b3a8261183c526f4e4ac3`.
It retains the original plan and its cumulative USD 1 ceiling. `gemma4:31b` is a targeted alternate
extractor for primary `NOT_JSON`/`SCHEMA_INVALID` calls with no valid answer. It never reads the
already successful primary calls. Mistral remains independent of both extractors. Gemma's dated
input/cached/output rates are 0.14/0.05/0.40 USD per million tokens; its conservative input ceiling
is 262,144 and thinking is off. No alternate-reader recovery is predicted or measured yet.

The six host attempts record USD 0.0054975 at the plan's conservative rates. The prior unknown-cost
attempt still reserves USD 0.339, so the unchanged cumulative budget accounts for USD 0.3444975.
Changing readers does not reset expenditure or discard failure provenance. The current post-harvest
audit is `store/pmc-screen-time/audits/question-round/590ae1dce65a257390aef02ec0d5324c03d22a78c1df9ad783c35a292bc78d84.json`.

Continue with:

```bash
.venv/bin/python tools/complete_question_round.py --plan store/pmc-screen-time/audits/q04-run-plan-v2.json --execute
```

The driver now harvests valid extraction/review in `finally`, even when another response interrupts
the lane. Three additional tests verify that partial successes reach the gate, that the alternate
reader only answers failed calls and skips successes on resume, and that mixed-reader costs and
unknown attempts share the original ceiling. Required checks: 889 tests, 7 skipped; six projects;
16 instrument versions unchanged. This agent made no additional network attempt in D51.
