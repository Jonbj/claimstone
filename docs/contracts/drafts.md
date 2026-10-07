# `drafts.jsonl` — operator reasoning drafts

**Written by:** the control server, `POST /control/v1/p/{p}/flows/{flow_id}/q/{question_id}/draft`
(B5). **Read by:** the same server's `GET …/draft`, for the operator who wrote it. **Never read by**
any stage, profile, verdict or export: `export.snapshot` excludes the file.

A draft is unfinished private text. The only judgement the project records is a signature in
`adjudications.jsonl`. The draft exists so that the reading desk can keep a person's reasoning
when the evidence profile changes under them. The page then says the profile changed and blocks
signing until the change is read.

| field | meaning |
|---|---|
| `draft_version` | `1` (`claimstone/drafts.py:DRAFT_VERSION`, registered as an instrument) |
| `flow_id` | the flow the operator was reading |
| `question_id` | the registry question |
| `rationale` | the text exactly as typed: not trimmed, no minimum, at most 20,000 characters |
| `profile_sha256` | the hash of the profile the operator was reading when they saved |
| `actor` | the operator id that held the session |
| `signer_auth` | always `"portal-session"` |
| `code_revision` | the control server's code revision, or `null` |
| `recorded_at` | UTC, seconds |

The latest row per (`actor`, `flow_id`, `question_id`) is the draft. A newer row supersedes an
older one; no row is edited.
