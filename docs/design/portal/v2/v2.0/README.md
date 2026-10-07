# Claimstone portal — redesign v2: the guided journey

**Status:** approved direction for the portal's user interface. It is a design, not an implementation.
**Date:** 2026-10-06.
**Reference boards:** the `.html` files in this folder. They are design-canvas sources: inline styles
plus a small runtime (`support.js`, `<x-dc>`) that is not in this repository. Read them as markup for
layout, copy and visual tokens; do not serve them. All values in them are illustrative; quoted passages
are placeholders.

## 1. Who the user is, and the promise

The user needs to gather what the scholarly literature says about a topic. They:

1. describe the topic in depth;
2. structure it as a set of questions;
3. press **Start**.

From then on Claimstone drives the project through every step. It shows constantly where the project
is, what Claimstone is doing, and the few points where it needs the user. A **scheduler** advances the
automatic steps; it is under development and is not part of this repository yet. The interface must
treat it as the actor behind every step marked "Claimstone".

Every human decision is taken **in the web interface**. The user never copies a command into a
terminal.

## 2. Rules the interface must keep

These come from `CLAUDE.md`. They are not style choices.

- **A verdict is a person's signature.** Only a person signs, through the reading desk (board 4).
  The interface never preselects a verdict, never suggests one, and no automated actor can sign.
- **There are five verdicts, and none collapses into another:** `SUPPORTED`, `CONTRADICTED`,
  `CONTESTED_IN_LITERATURE`, `UNANSWERED_IN_LITERATURE`, `NEVER_ASKED`.
  - Engine states such as `NO_VERIFIED_CLAIM` are not verdicts.
  - A question whose reading is unfinished is shown as **"still being read"**, never as "nothing
    found".
  - A question without a profile is never shown as awaiting a person.
- **No floor, no verdicts.** If Claimstone could not obtain the declared share of the sources it
  found (the acquisition floor), the project produces no verdicts. The interface says what is
  missing; it offers no override.
- **The protocol is frozen when the user starts.** Topic and questions become version 1, dated. A
  later change creates version 2 and never silently edits version 1.
- **Unknown is not zero.** A value that cannot be known shows "—". A value still being computed
  shows a pending state. Only a counted zero shows "0".
- **Counts are counts.** "1 supports, 1 contradicts" is labelled as a count, not a strength.
  Per-source-class counts come before pooled totals.
- **HTTP 403 means "access refused".** It is never labelled a paywall or proof that a copy can be
  bought.
- **Nothing runs or spends without consent.** Network campaigns and paid model work start only after
  the user approves them in the interface, within the limits shown.
- **Meaning is decided on the server.** States, labels, counts and the next valid action come from
  the API. The browser renders them and never re-derives them.

## 3. Visual system

| element | choice |
|---|---|
| layout | dark left sidebar (232–260 px, `#0f172a`); content on `#f4f5f7`; white cards with 16–18 px radius and a light shadow |
| type | **Instrument Serif** for page titles, topic titles and question statements (a question is a claim, so it reads as one); **Geist** for the interface; **Geist Mono** for identifiers, hashes and counts |
| colour meaning (fixed) | violet `#7c3aed` = waits for you · blue `#2563eb`/`#1e40af` = Claimstone, and CONTRADICTS (blue, never red: concluding against a question is a result, not a failure) · emerald `#059669` = done, confirmed, SUPPORTS · amber `#d97706` = still being read, provisional · rose `#e11d48` = not obtained, below floor · slate = neutral, QUALIFIES |
| actors | every step and decision is marked **Claimstone** (blue) or **you** (violet) |
| accessibility | real buttons, links and form controls; 44 px touch targets; colour never carries meaning alone (every chip has its word) |

The implementation uses the stack already in `web/`: React, shadcn/ui, Tremor Raw and Tailwind, with
fonts bundled and no CDN.

## 4. Navigation (every page)

The sidebar never lists all projects; a user will have hundreds after a few years. It holds, in order:

1. **New project** (primary button);
2. **Today**;
3. **Projects**;
4. **Decisions**, with a badge counting open decisions;
5. a **Pinned** section with at most 5 projects the user chose;
6. **Administration**, at the bottom;
7. a footer with the signed-in user's name and the scheduler's status ("scheduler on / paused /
   off").

## 5. The boards

### Board 1 — Projects (`V2Projects.html`)

**Purpose:** the archive of every project, and a way to see at once which ones need the user.

**Contents:**
- Title and a summary line: total, running, waiting for you, finished.
- A **search** field (topic, question or keyword) and **status filters**: All · Waiting for you ·
  Running · Finished · Drafts.
- A table with one row per project:

  | column | content |
  |---|---|
  | project | name, with the topic in one line beneath |
  | where it is | a sentence chip, e.g. "Waiting for you · sign Q04", "Running · obtaining copies", "Waiting for you · below floor", "Draft" |
  | progress | an 8-segment bar for the 8 journey steps: emerald done, blue running, violet waiting for you, rose blocked, grey not started; beneath it, "step N of 8" plus the current detail (e.g. "23 of 40") |
  | questions | number of questions, and how many are ready to sign |
  | last activity | when the project last changed |

- Default sort: projects waiting for the user first, then by last activity. Pagination or infinite
  scroll ("showing N of M").

**Use:** clicking a project opens its journey page (board 3). "+ New project" opens board 2.

### Board 2 — New project (`V2NewProject.html`)

**Purpose:** the one moment when the user says what they need to know.

**Contents:**
- **Step rail (left), four steps:**
  1. Describe the topic;
  2. Ask the questions;
  3. Sources and rigour;
  4. Review and start.

  Done steps show a check, the current one is highlighted. The draft is saved automatically and
  nothing runs until the user starts.
- **Step 1, the topic:** title, an in-depth description, and the scope (what is in, what is out).
  The board shows it completed and summarised with an Edit link.
- **Step 2, the questions (shown open):**
  - Each question is a card. It has an identifier (Q01, Q02…) and a **kind** selector: effect,
    heterogeneity, method, premise or operational. The kind decides which rule judges the
    question; a one-line hint explains it.
  - The statement is a multi-line field in the serif face. Guidance: write each question as a
    statement the literature can support or contradict.
  - A **vague question** is flagged in amber with a concrete suggestion. Example: "News works." →
    "Say what works, for whom, and how you would know — for example a horizon and an outcome."
  - "+ Add a question". Back / "Continue to sources".
- **Step 3, sources and rigour** (not drawn): which source classes count, and the **acquisition
  floor** (the share of found sources that must be read before any verdict), each with a plain
  explanation and a default.
- **Step 4, review and start** (not drawn): a summary of topic, questions, sources and floor, and
  the **Start** button. Starting freezes the protocol as version 1.
- **Side panel, "What happens when you start":** the journey in seven lines, each marked C
  (Claimstone) or Y (you):
  - Y: freeze the protocol;
  - C: search;
  - C: obtain legal copies (you approve retries and may upload copies);
  - C: read and annotate, with each claim checked against its quote;
  - Y: approve the reading budget;
  - C: independent review, then one evidence profile per question;
  - Y: read and sign.

  Beneath it, the rule that does not move: below the floor, no verdicts; Claimstone says what is
  missing.

**Use:** fill the steps in order, then press Start. The project appears in Projects as running.

### Board 3 — Project journey (`V2Journey.html`)

**Purpose:** the project's home page from start to verdicts. It shows where the project is, who is
acting, and what is needed from the user.

**Contents:**
- **Header:**
  - breadcrumb and project title (serif);
  - status chips ("Waiting for you · 2 decisions", "Step 6 of 8");
  - the 8-segment journey bar. There is no single percentage of completion; steps are the unit.
- **The journey (main column):** the 8 steps as a vertical timeline. Each step shows its number or
  ✓, its title, its actor (Claimstone or you), a date, and a one-sentence plain summary.

  | step | title | actor | summary or behaviour |
  |---|---|---|---|
  | 1 | Protocol frozen | you | e.g. "Topic and 8 questions, version 1. Floor: 80% of the sources found must be read." |
  | 2 | Search the literature | Claimstone | e.g. "40 sources found by keyword and citations. How much exists in the world is not knowable; this is what was found." |
  | 3 | Obtain legal copies | Claimstone | e.g. "37 of 40 confirmed — floor met. 2 refused, 1 not a document", plus an optional link to retry or upload the refused ones |
  | 4 | Read the documents | Claimstone | documents parsed into passages |
  | 5 | Annotate every passage | Claimstone | annotations kept, and how many were rejected because their quote or numbers did not check out |
  | 6 | Approve the review budget | you | when waiting: expanded and tinted violet (see below) |
  | 7 | Independent review and profiles | Claimstone | "starts when step 6 is approved", plus what is already done |
  | 8 | Read and sign the verdicts | you | how many questions are ready, and a "Read and sign Qnn" button |

  At step 6 the expanded panel shows the figures needed to decide (number of calls, reserved spending
  ceiling, reader model) and three buttons: **Approve and continue**, **Change ceiling**, **Not now**.
- **Side column:**
  - **Right now** (dark card): what the scheduler is doing at this moment, or why it is paused (e.g.
    "paused, waiting for your decision on the review budget; nothing will be spent until you approve
    it"), and the time of the last activity.
  - **The topic:** the description and scope, the protocol version and freeze date, and "Propose a
    change (creates version 2)".
  - **The questions:** each question in serif with its state chip ("being read", "ready to sign",
    later "signed: CONTRADICTED"); a link to all questions.
  - **Evidence so far:** sources read / found, annotations, reviewed; a link to the evidence path
    (board 6).

**Use:** the page updates live while the scheduler works. When a step needs the user, it expands in
place with its decision controls; decisions can also be taken from board 5.

### Board 4 — Reading desk with signature (`V2Desk.html`)

**Purpose:** a person reads the evidence for one question and signs its verdict, in the page.

**Contents:**
- **Sidebar:** back to the project; the list of questions ready to sign. The others appear as their
  review completes.
- **Header:**
  - question identifier, kind, and a "final · admissible" chip;
  - the question statement (serif, large);
  - a one-line summary, e.g. "4 of 37 sources speak to it: 1 supports, 1 contradicts, 2 qualify. A
    count, not a strength."
- **Reading progress:** "You have opened N of M results", as small segments.
- **Results:** one card per result. Each card has:
  - the stance chip (Supports emerald, Contradicts blue, Qualifies slate);
  - the source identifier and class;
  - the claim sentence;
  - the **verbatim quote**, verified in code against the source passage;
  - the independent reader's label;
  - a "Provenance →" link (board 7).

  Unopened results are collapsed to one line with "Open".
- **Signature form (right):**
  - **Verdict:** the five verdicts as radio options, each with a one-line definition. **None is
    preselected.** The board shows one chosen only to display the selected style.
  - **Your reasoning:** a text area with a live character count. At least 120 characters; the
    reasoning is the verdict's only defence.
  - A checkbox: "I have read all M results and their passages."
  - **Sign as [operator name]:** enabled only when every result has been opened and the box is
    ticked. The signer's identity comes from authentication, not from a typed name.
  - A footnote: the signature is bound to this exact profile (its hash). If the evidence changes
    later, the signature is marked stale, never silently kept.

**Use:** open each result, read it, choose a verdict, write the reasoning, tick the box, sign. If the
profile changed since the page loaded, the server refuses and the page asks the user to read again.

### Board 5 — Decisions (`V2Decisions.html`)

**Purpose:** every decision waiting for the user, across all projects, each one actionable in place.
The scheduler waits on each one.

**Contents:** one card per decision, each with a type chip, the project and step, how long it has
waited, and its controls.

| decision | controls |
|---|---|
| **Approve a budget** | what will run (e.g. independent review of 1,679 annotations); a **spending ceiling** field; Approve / Decline. Work stops before any call that would exceed the ceiling, and calls of unknown cost are reserved, not guessed |
| **Authorize a retry campaign** | the refused sources, each with a checkbox and its reason (e.g. "bot challenge on the publisher host"; "HTTP 403 — access refused, not proof of a paywall"); the exact scope ("at most N requests to K hosts, robots.txt honoured, recorded as campaign <name>"); "Authorize N sources". Marked optional when the floor is already met |
| **Provide a copy** | for a project below its floor, a drop zone for PDFs the user legally holds. Every file is hashed, checked against the source's identity and passed through the same content gate as a download; a mismatch is shown, never silently accepted |
| **Resolve an identity** | two records side by side (e.g. the index's metadata and the held PDF's first page) and four answers: Same work · A version of it · Different works · Not sure — keep pending |
| **Sign** | the question statement and "Read and sign", which opens board 4 |

**Use:** take decisions in any order. Each one records who decided and when, and releases the
scheduler for that project.

### Board 6 — Evidence path (`Flow.html`, from the first proposal, still valid)

**Purpose:** the numeric detail behind a project, reached from "Evidence so far" on board 3.

**Contents:**
- A **funnel**: sources found → obtained → confirmed documents → annotations kept → independently
  reviewed → evidence profiles. Each column has its count, its label and what was lost at that step
  (e.g. "2 not obtained", "271 rejected by the gate").
- Questions as cards: state, serif statement, direction counts, coverage.
- The acquisition floor as a ring with the floor value and per-class rows; a source tracker (one
  block per source, coloured by state); a "needs you here" box.

In v2 its sidebar follows section 4, and "needs you here" links to board 5.

### Board 7 — Claim provenance (`Lineage.html`, from the first proposal, still valid)

**Purpose:** verify a single piece of evidence down to its source, reached from "Provenance →" on a
result card.

**Contents:**
- the claim statement and its stance;
- a **six-step chain**: candidate → acquired copy → document → passage → claim → review, each with a
  one-line fact;
- **the passage** the claim was checked against, with the quote highlighted where the gate found it,
  and a badge "quote found verbatim · every number in the claim is in the quote";
- side cards for the independent review (label and reason, verbatim), who read it (extractor,
  harness version, reviewer), and the copy (licence, route, attempts), linking to the source
  dossier.

## 6. The whole flow

**Projects → New project → Start.** The journey page then shows Claimstone's progress and stops where
the user is needed. The user decides there or in **Decisions** (budget, retry campaign, copies,
identities). When a question is ready, the **reading desk** is where they read and sign. The
**evidence path** and **claim provenance** pages verify any number or quote down to the source.

## 7. What the backend must provide

The current portal is read-only by decision (D82, D84). This design needs the following before any
control can work. The design review `docs/superpowers/specs/2026-10-06-research-portal-review.md`
records them as phases P3/P4.

| need | why |
|---|---|
| **Authenticated identity** | a signature and every authorization must name a signed-in person, not a typed name. The adjudication record needs a field saying how the signer was authenticated (a decision-contract version bump) |
| **One writer lock** | the web interface, the scheduler and the CLI must never write the same project's ledgers at the same time |
| **New append-only records** | project drafts and protocol versions, budget approvals (with ceiling), authorized campaigns (with exact scope), uploaded copies (hash, identity check, outcome), identity decisions, and the operations the scheduler runs (with resumable state) |
| **The scheduler's interface** | Start, Approve and Authorize become operations the scheduler picks up. The journey reads the scheduler's state: running, paused waiting for the user, failed, done |
| **Upload safety** | uploaded files are stored by hash in quarantine and pass identity and content checks before they count. Whether operator-supplied copies count toward the floor is a policy the user declares per project, in advance |
| **URL safety** | any address the user supplies is checked (no private or local hosts) before Claimstone fetches it |
| **Server-side meaning** | the journey steps and their states, the "right now" sentence, decision cards and their scopes, question states, and the result cards' reviewer labels all come from the API. The browser renders them as received |
| **Web security** | sessions, CSRF protection on every change, and the existing Host/Origin checks and loopback-only binding |
