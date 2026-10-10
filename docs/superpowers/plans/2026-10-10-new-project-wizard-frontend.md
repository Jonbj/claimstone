# New-project wizard — frontend Implementation Plan (plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A bilingual (Italian/English) four-step wizard in the portal that explains every phase and what Claimstone will do after each save, builds a draft through the control routes of plan 1, and creates a frozen project on confirmation, starting nothing.

**Architecture:** The portal's i18n infrastructure (local JSON catalogs, `t()`), a `ControlError` that carries field-path details, typed `control.new*` methods, a wizard shell with a right-hand explanation panel (an accordion under 900 px), four step forms and two pages (`/new`, `/new/:draft/:step`). Figures shown in the panel come from the server and render "—" when unknown.

**Tech Stack:** React 19, react-router 7, Tailwind 4, Vitest 3 + Testing Library (jsdom), TypeScript strict. No new dependency.

**Depends on:** plan 1 (`2026-10-10-new-project-wizard-backend.md`) — the routes of `docs/contracts/new_project.md`.

**Rules of this codebase that bind this plan** (checked by existing tests): only `src/lib/control.ts` sends a non-GET request or calls `fetch`; every `<form>` has an `onSubmit` that calls `preventDefault()` (the CSP has `form-action 'none'`); **no inline `style` attributes** (the CSP's `style-src 'self'`); the CSRF token never reaches storage; unknown is "—", never 0; colour never carries meaning alone. Run from `web/`: `npm run typecheck`, `npm test`, `npm run build`.

**Spec note (correction found while planning):** the spec places "Advanced" in step 3. It edits the *generated files*, which exist only once steps 1–3 are saved, so it lives in step 4. Task 0 corrects the spec.

---

## File structure

| File | Responsibility |
|---|---|
| `web/src/lib/control.ts` (modify) | `ControlError.details`; wizard types; `control.new*` methods |
| `web/src/lib/i18n.tsx` (create) | `LocaleProvider`, `useLocale`, `translate`, `flatten`, `initialLocale` |
| `web/src/messages/en.json`, `it.json` (create) | The catalogs (software copy only; user text never enters them) |
| `web/src/components/LocaleSwitch.tsx` (create) | EN/IT buttons for the sidebar footer |
| `web/src/components/wizard/figures.ts` (create) | `show`, `explainParams` (unknown → "—") |
| `web/src/components/wizard/problems.tsx` (create) | `problemsOf`, `FieldError`, `ErrorSummary` |
| `web/src/components/wizard/useWide.ts` (create) | the 900 px breakpoint as a hook |
| `web/src/components/wizard/ExplainPanel.tsx`, `WizardShell.tsx` (create) | the layout and "what Claimstone will do" |
| `web/src/components/wizard/StepTopic.tsx`, `StepQuestions.tsx`, `StepSources.tsx`, `StepReview.tsx` (create) | the four steps |
| `web/src/pages/NewProjectsPage.tsx`, `WizardPage.tsx` (create) | `/new` and `/new/:draft/:step` |
| `web/src/App.tsx`, `web/src/components/Shell.tsx` (modify) | routes, the live "+ New project" link, the language switch, the provider |
| `web/tests/*.test.ts(x)` (create/modify) | one test file per concern |
| `tools/check_new_project_wizard.py` (create) | the live check: drives the routes against a temp workspace |
| `docs/GUIDE.md`, `docs/GUIDE.it.md` (modify) | "Create a project from the portal" |

---

### Task 0: Correct the spec (Advanced lives in step 4)

**Files:** Modify `docs/superpowers/specs/2026-10-10-new-project-wizard-design.md`

- [ ] **Step 1: Apply**

```bash
python3 - <<'PY'
p = "docs/superpowers/specs/2026-10-10-new-project-wizard-design.md"
s = open(p, encoding="utf-8").read()
old = "the field's notation (`extraction.value_labels`); extra excluded hosts; Advanced |"
new = "the field's notation (`extraction.value_labels`); extra excluded hosts |"
assert old in s; s = s.replace(old, new)
old = "| **4 · Review and create** | confirmation |"
new = "| **4 · Review and create** | confirmation; **Advanced**: edit the generated files (they exist only once steps 1–3 are saved; an edit replaces a whole file and must still load) |"
assert old in s; s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
PY
git add docs/superpowers/specs/2026-10-10-new-project-wizard-design.md
git commit -m "spec: Advanced lives in step 4, where the generated files exist

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 1: `ControlError.details` and the typed wizard methods

**Files:**
- Modify: `web/src/lib/control.ts`
- Test: `web/tests/control.test.ts`

- [ ] **Step 1: Write the failing tests** (append inside the existing `describe("F1: control client transport", …)` block of `web/tests/control.test.ts`, before its closing `});`)

```ts
  it("keeps the field-path details of a 422", async () => {
    setCsrfToken("tok");
    mockFetch(reply(422, { error: { code: "VALIDATION", message: "name: bad",
      details: [{ path: "name", message: "use lowercase" }] } }));
    const error = await control.newSaveStep("d1", 1, 1, {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ControlError);
    expect((error as ControlError).details).toEqual([{ path: "name", message: "use lowercase" }]);
  });

  it("an error without details has an empty list", async () => {
    setCsrfToken("tok");
    mockFetch(reply(409, { error: { code: "STALE_REVISION", message: "old" } }));
    const error = await control.newSaveStep("d1", 1, 1, {}).catch((e: unknown) => e);
    expect((error as ControlError).details).toEqual([]);
  });

  it("the new-project methods use their routes, the CSRF token and an Idempotency-Key", async () => {
    setCsrfToken("tok");
    mockFetch(reply(200, {}));
    await control.newStart();
    await control.newSaveStep("d 1", 2, 5, { a: 1 });
    await control.newSaveAdvanced("d1", 6, { "sources.yaml": "x" });
    await control.newDiscard("d1", 7);
    await control.newCreate("d1");
    expect(calls.map((c) => `${c.init.method} ${c.url}`)).toEqual([
      "POST /control/v1/new",
      "POST /control/v1/new/d%201/steps/2",
      "POST /control/v1/new/d1/advanced",
      "POST /control/v1/new/d1/discard",
      "POST /control/v1/new/d1/create",
    ]);
    for (const call of calls) {
      expect(headersOf(call)["X-CSRF-Token"]).toBe("tok");
      expect(headersOf(call)["Idempotency-Key"]).toBeTruthy();
    }
    expect(JSON.parse(String(calls[1].init.body))).toEqual({ base_revision: 5, data: { a: 1 } });
    expect(JSON.parse(String(calls[4].init.body))).toEqual({ confirm: true });
  });

  it("the new-project reads are plain GETs", async () => {
    mockFetch(reply(200, {}));
    await control.newDrafts();
    await control.newRead("d1");
    await control.newPreview("d1");
    await control.newTemplates();
    await control.newTemplate("general");
    expect(calls.map((c) => `${c.init.method} ${c.url}`)).toEqual([
      "GET /control/v1/new", "GET /control/v1/new/d1", "GET /control/v1/new/d1/preview",
      "GET /control/v1/new-templates", "GET /control/v1/new-templates/general",
    ]);
  });
```

- [ ] **Step 2: Run to verify failure**

Run (from `web/`): `npx vitest run tests/control.test.ts`
Expected: FAIL (`control.newSaveStep is not a function`).

- [ ] **Step 3: Implement in `web/src/lib/control.ts`**

3a. Replace the `ControlError` class with:

```ts
export interface FieldProblem {
  path: string;
  message: string;
}

export class ControlError extends Error {
  readonly status: number;
  readonly code: string;
  readonly message: string;
  /** Field paths of a 422, or an empty list. */
  readonly details: FieldProblem[];

  constructor(status: number, code: string, message: string, details: FieldProblem[] = []) {
    super(`[${code}] ${message}`);
    this.name = "ControlError";
    this.status = status;
    this.code = code;
    this.message = message;
    this.details = details;
  }
}
```

3b. In `parse`, change the `Envelope` type and the throw:

```ts
type Envelope = { error?: { code?: string; message?: string; details?: FieldProblem[] } };
```
```ts
    throw new ControlError(response.status, String(body.error.code ?? "UNKNOWN"),
                           String(body.error.message ?? ""),
                           Array.isArray(body.error.details) ? body.error.details : []);
```

3c. After the `// --- types, by route ---` section's existing types, add:

```ts
// new project (plan 1; docs/contracts/new_project.md)
export type Figures = Record<string, unknown>;

export interface WizardTemplateSummary {
  id: string;
  label: string;
  description: string;
}

export interface WizardTemplate {
  id: string;
  label: string;
  default_floor: number;
  classes: Array<{ id: string; name: string; weight_hint: string; notes: string }>;
  excluded_hosts: string[];
  notation_presets: Array<{ id: string; label: string }>;
}

export interface DraftSummary {
  draft_id: string;
  status: "open" | "discarded" | "created";
  revision: number;
  steps_saved: number[];
  project_name: string | null;
  project: string | null;
  updated_at: string;
}

export interface DraftState {
  draft_id: string;
  revision: number;
  status: "open" | "discarded" | "created";
  steps: Record<string, { data: Row; revision: number }>;
  advanced: Record<string, string>;
  figures: Record<string, Figures>;
  project: string | null;
  last_failure: string | null;
  started_at: string;
  updated_at: string;
}

export interface StepSaved {
  revision: number;
  data: Row;
  figures: Figures;
}

export interface Preview {
  figures: Figures;
  protocol_sha256: string;
  files: Record<string, string>;
  revision: number;
}

export interface Created {
  project: string;
  protocol_sha256: string;
  files: Record<string, string>;
  frozen: { registry_version: number; frozen_at: string; floor_version: number };
}
```

3c-bis. Add these members inside the `control` object, after `resolveIntake`:

```ts
  // new project
  newTemplates: () => get<{ templates: WizardTemplateSummary[] }>("/new-templates"),
  newTemplate: (id: string) => get<WizardTemplate>(`/new-templates/${enc(id)}`),
  newDrafts: () => get<{ drafts: DraftSummary[] }>("/new"),
  newStart: () => post<{ draft_id: string; revision: number }>("/new", {}),
  newRead: (id: string) => get<DraftState>(`/new/${enc(id)}`),
  newSaveStep: (id: string, step: number, baseRevision: number, data: unknown) =>
    post<StepSaved>(`/new/${enc(id)}/steps/${step}`, { base_revision: baseRevision, data }),
  newSaveAdvanced: (id: string, baseRevision: number, files: Record<string, string>) =>
    post<{ revision: number }>(`/new/${enc(id)}/advanced`, { base_revision: baseRevision, files }),
  newPreview: (id: string) => get<Preview>(`/new/${enc(id)}/preview`),
  newDiscard: (id: string, baseRevision: number) =>
    post<{ revision: number; status: string }>(`/new/${enc(id)}/discard`, { base_revision: baseRevision }),
  newCreate: (id: string) => post<Created>(`/new/${enc(id)}/create`, { confirm: true }),
```

- [ ] **Step 4: Run to verify pass, then typecheck**

Run: `npx vitest run tests/control.test.ts && npm run typecheck`
Expected: pass; no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/control.ts web/tests/control.test.ts
git commit -m "web: ControlError carries field-path details; typed new-project methods

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 2: The i18n infrastructure

Per the design approved on 2026-10-07: local JSON catalogs, `t("key", params)`, a missing key shows itself (never an invented label), software copy only. `useLocale()` works without a provider (English), so existing tests keep passing.

**Files:**
- Create: `web/src/lib/i18n.tsx`, `web/src/components/LocaleSwitch.tsx`, `web/src/messages/en.json`, `web/src/messages/it.json` (a first slice: `shell` only; Task 3 adds the wizard)
- Test: `web/tests/i18n.test.tsx`

- [ ] **Step 1: Write the failing tests** `web/tests/i18n.test.tsx`

```tsx
// i18n: the catalogs agree, a missing key shows itself, the choice survives blocked storage.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LocaleSwitch from "@/components/LocaleSwitch";
import {
  CATALOGS, LocaleProvider, STORAGE_KEY, flatten, initialLocale, translate, useLocale,
} from "@/lib/i18n";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("catalogs", () => {
  it("have exactly the same keys in both locales", () => {
    expect(Object.keys(CATALOGS.it).sort()).toEqual(Object.keys(CATALOGS.en).sort());
  });

  it("use the same placeholders in both locales", () => {
    for (const key of Object.keys(CATALOGS.en)) {
      expect([key, placeholders(CATALOGS.it[key])]).toEqual([key, placeholders(CATALOGS.en[key])]);
    }
  });

  it("have no empty text", () => {
    for (const locale of ["en", "it"] as const) {
      for (const [key, text] of Object.entries(CATALOGS[locale])) {
        expect([locale, key, text.trim().length > 0]).toEqual([locale, key, true]);
      }
    }
  });
});

describe("translate", () => {
  it("fills placeholders and leaves an unknown one visible", () => {
    expect(translate("en", "shell.language")).toBe("Language");
    expect(flatten({ a: { b: "x" } })).toEqual({ "a.b": "x" });
    expect(translate("en", "no.such.key")).toBe("no.such.key"); // never an invented label
  });
});

describe("initialLocale", () => {
  it("follows the browser, English by default", () => {
    vi.stubGlobal("navigator", { language: "it-IT" });
    expect(initialLocale()).toBe("it");
    vi.stubGlobal("navigator", { language: "fr-FR" });
    expect(initialLocale()).toBe("en");
  });

  it("prefers the remembered choice", () => {
    vi.stubGlobal("navigator", { language: "en-US" });
    localStorage.setItem(STORAGE_KEY, "it");
    expect(initialLocale()).toBe("it");
  });

  it("survives blocked storage", () => {
    vi.stubGlobal("navigator", { language: "it" });
    vi.stubGlobal("localStorage", { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } });
    expect(initialLocale()).toBe("it");
  });
});

function Probe() {
  const { t, locale } = useLocale();
  return <p data-testid="probe">{locale}:{t("shell.language")}</p>;
}

describe("LocaleProvider and LocaleSwitch", () => {
  it("switches the language, the html lang and the remembered choice", () => {
    vi.stubGlobal("navigator", { language: "en-US" });
    render(<LocaleProvider><LocaleSwitch /><Probe /></LocaleProvider>);
    expect(screen.getByTestId("probe").textContent).toBe("en:Language");
    fireEvent.click(screen.getByRole("button", { name: "IT" }));
    expect(screen.getByTestId("probe").textContent).toBe("it:Lingua");
    expect(document.documentElement.lang).toBe("it");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("it");
    expect(screen.getByRole("button", { name: "IT" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("works without a provider, in English", () => {
    render(<Probe />);
    expect(screen.getByTestId("probe").textContent).toBe("en:Language");
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/i18n.test.tsx`
Expected: FAIL (cannot resolve `@/lib/i18n`).

- [ ] **Step 3: Implement**

`web/src/messages/en.json` (the slice for now):

```json
{
  "shell": {
    "newProject": "+ New project",
    "language": "Language"
  }
}
```

`web/src/messages/it.json`:

```json
{
  "shell": {
    "newProject": "+ Nuovo progetto",
    "language": "Lingua"
  }
}
```

`web/src/lib/i18n.tsx`:

```tsx
// Portal i18n (approved 2026-10-07): software labels only, local JSON catalogs, no runtime fetch.
// What a person types (project name, topics, terms, questions, rationales) and what the engine
// reports (claims, quotes) never passes through `t()`. A key that is missing shows itself: a
// visible bug is better than an invented label. Contract tokens (SUPPORTED, effect, …) stay
// canonical and are glossed beside, never replaced.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import en from "@/messages/en.json";
import it from "@/messages/it.json";

export const LOCALES = ["en", "it"] as const;
export type Locale = (typeof LOCALES)[number];
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", it: "Italiano" };
export type Messages = { [key: string]: string | Messages };
export type Params = Record<string, string | number>;

export const STORAGE_KEY = "claimstone-locale";

export function flatten(messages: Messages, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(messages)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out[path] = value;
    else Object.assign(out, flatten(value, path));
  }
  return out;
}

export const CATALOGS: Record<Locale, Record<string, string>> = {
  en: flatten(en as Messages),
  it: flatten(it as Messages),
};

export function translate(locale: Locale, key: string, params?: Params): string {
  const text = CATALOGS[locale][key];
  if (text === undefined) return key;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) =>
    params && name in params ? String(params[name]) : whole);
}

export function initialLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "it") return stored;
  } catch {
    // Storage can be blocked or absent; the page works without remembering.
  }
  const language = typeof navigator === "undefined" ? "" : String(navigator.language ?? "");
  return language.toLowerCase().startsWith("it") ? "it" : "en";
}

export interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, params?: Params) => string;
}

const FALLBACK: LocaleState = {
  locale: "en",
  setLocale: () => undefined,
  t: (key, params) => translate("en", key, params),
};

const LocaleContext = createContext<LocaleState>(FALLBACK);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not remembered; still switched.
    }
  }, []);

  const value = useMemo<LocaleState>(
    () => ({ locale, setLocale, t: (key, params) => translate(locale, key, params) }),
    [locale, setLocale],
  );
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleState {
  return useContext(LocaleContext);
}
```

`web/src/components/LocaleSwitch.tsx`:

```tsx
import { LOCALES, useLocale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

// Two buttons, the current one pressed; the language's own name is the label, in that language.
export default function LocaleSwitch() {
  const { locale, setLocale, t } = useLocale();
  return (
    <div role="group" aria-label={t("shell.language")} className="flex gap-1">
      {LOCALES.map((code) => (
        <button
          key={code}
          type="button"
          lang={code}
          aria-pressed={locale === code}
          onClick={() => setLocale(code)}
          className={cn(
            "min-h-8 rounded-md border border-rail-border px-2 text-xs",
            locale === code
              ? "bg-rail-active font-medium text-rail-foreground"
              : "text-rail-muted hover:text-rail-foreground",
          )}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify pass, then typecheck**

Run: `npx vitest run tests/i18n.test.tsx && npm run typecheck`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/i18n.tsx web/src/components/LocaleSwitch.tsx web/src/messages web/tests/i18n.test.tsx
git commit -m "web: portal i18n infrastructure (local JSON catalogs, t(), language switch)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 3: The catalogs — every phase explained, in Italian and English

This is the content the operator reads. Replace both files in full. The parity test of Task 2 enforces that both have the same keys and placeholders. **Placeholders** are filled from server figures; an unknown figure renders "—".

**Files:** Modify `web/src/messages/en.json`, `web/src/messages/it.json`; Test: `web/tests/wizardcopy.test.ts`

- [ ] **Step 1: Write the failing test** `web/tests/wizardcopy.test.ts`

```ts
// The copy the wizard shows is complete: every step has its three explanations, every kind and
// every state has a gloss, and the five contract tokens survive translation untouched.
import { describe, expect, it } from "vitest";
import { CATALOGS } from "@/lib/i18n";

describe("wizard copy", () => {
  it("explains every step in three moments, in both languages", () => {
    for (const locale of ["en", "it"] as const) {
      for (const step of [1, 2, 3, 4]) {
        for (const moment of ["afterSave", "atCreation", "afterStart"]) {
          expect(CATALOGS[locale][`wizard.step${step}.${moment}`]).toBeTruthy();
        }
      }
    }
  });

  it("glosses every question kind and every draft status", () => {
    for (const locale of ["en", "it"] as const) {
      for (const kind of ["effect", "heterogeneity", "method", "premise", "operational"]) {
        expect(CATALOGS[locale][`wizard.kind.${kind}`]).toBeTruthy();
      }
      for (const status of ["open", "discarded", "created"]) {
        expect(CATALOGS[locale][`wizard.drafts.status.${status}`]).toBeTruthy();
      }
    }
  });

  it("keeps contract tokens canonical inside the prose", () => {
    for (const locale of ["en", "it"] as const) {
      expect(CATALOGS[locale]["wizard.step3.afterStart"]).toContain("INSUFFICIENT_ACQUISITION");
      expect(CATALOGS[locale]["wizard.kind.operational"]).toContain("operational");
    }
  });

  it("never promises a verdict for an operational question", () => {
    for (const locale of ["en", "it"] as const) {
      expect(CATALOGS[locale]["wizard.step2.atCreation"]).toContain("{operational}");
    }
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/wizardcopy.test.ts`
Expected: FAIL (keys missing).

- [ ] **Step 3: Write `web/src/messages/en.json`**

```json
{
  "shell": {
    "newProject": "+ New project",
    "language": "Language"
  },
  "wizard": {
    "title": "New project",
    "lede": "Describe a topic, ask your questions, declare the sources and the bar. Claimstone checks each step and keeps a draft. Nothing runs until you create the project, and creating it does not start any research.",
    "signIn": "Sign in to create a project.",
    "signInLink": "Sign in",
    "loading": "Loading the draft…",
    "back": "Back",
    "saveContinue": "Save and continue",
    "saving": "Saving…",
    "draftNote": "Draft saved · nothing runs until you create the project",
    "problems": "Please fix these before continuing:",
    "stale": "This draft was changed elsewhere. Reload it to see the latest version.",
    "reload": "Reload the draft",
    "discarded": "This draft was discarded. Nothing was created.",
    "backToDrafts": "Back to your drafts",
    "rail": {
      "label": "Steps",
      "done": "done",
      "current": "current"
    },
    "steps": {
      "1": { "name": "Topic", "hint": "what you need to know, and why" },
      "2": { "name": "Questions", "hint": "literature questions get a verdict you sign" },
      "3": { "name": "Sources and rigour", "hint": "where evidence may come from, and the bar" },
      "4": { "name": "Review and create", "hint": "freeze the protocol" }
    },
    "explain": {
      "title": "What Claimstone will do",
      "afterSave": "After you save this step",
      "atCreation": "When you create the project",
      "afterStart": "After you start research (next stage)"
    },
    "drafts": {
      "title": "Your drafts",
      "empty": "You have no drafts yet.",
      "start": "Start a new project",
      "resume": "Continue",
      "discard": "Discard",
      "untitled": "Untitled draft",
      "stepsSaved": "{n} of 3 steps saved",
      "openProject": "Open the project",
      "status": {
        "open": "open",
        "discarded": "discarded",
        "created": "created"
      }
    },
    "kind": {
      "effect": "effect — judged on results that test it: estimates, uncertainty, horizon, sample, design.",
      "heterogeneity": "heterogeneity — judged on the contrast between subgroups, with its uncertainty and whether the subgroup analysis was prespecified.",
      "method": "method — judged on what kind of support each source gives the methodological claim.",
      "premise": "premise — judged on the explicit statement of it, or a contradiction of it.",
      "operational": "operational — tracked in this project; no literature verdict applies, and it is never shown as awaiting your signature."
    },
    "step1": {
      "title": "1 · The topic",
      "intro": "Name the project and list what to search for. Terms are broad on purpose: their job is to find works, not to define what is learned.",
      "name": "Project name",
      "nameHelp": "2 to 63 lowercase letters, digits or hyphens. It becomes the folder name and cannot be changed.",
      "description": "What you need to know, and why (optional)",
      "descriptionHelp": "In scope and out of scope, in a few sentences. It is kept with the project and read by no stage.",
      "topics": "Topics",
      "topicLabel": "Topic",
      "terms": "Search terms, one per line",
      "termsHelp": "Each term is searched as written.",
      "addTopic": "Add a topic",
      "removeTopic": "Remove this topic",
      "afterSave": "Claimstone checks the name and the topics, then keeps a draft. Nothing is created and nothing runs.",
      "atCreation": "Each search term will become one query on each index you choose later. So far: {terms} terms in {topics} topics, which means {searches} searches per index, or {searchesAll} if all three indexes are used.",
      "afterStart": "Terms find works; they do not define what is learned. Widening a topic is cheap and cannot by itself change a verdict."
    },
    "step2": {
      "title": "2 · The questions",
      "intro": "Write each literature question as a statement the literature can support or contradict. Claimstone does not judge your wording: it only checks that a question is not empty and has a kind.",
      "question": "Question",
      "kind": "Kind",
      "addQuestion": "Add a question",
      "removeQuestion": "Remove this question",
      "afterSave": "Claimstone checks each question and keeps a draft. The questions are not frozen yet, so you can still change them.",
      "atCreation": "The question registry is frozen at version 1, dated today. {literature} of your {total} questions are literature questions: each will get an evidence profile that a person reads and signs. {operational} are operational: tracked, but they never receive a verdict. Changing the registry later is a dated version bump, never a silent edit.",
      "afterStart": "Each kind is judged by its own rule. Claimstone reads sources with these questions in mind and extracts claims, each bound to a verbatim quote that code checks."
    },
    "step3": {
      "title": "3 · Sources and rigour",
      "intro": "Declare which kinds of source may count and the bar a round must clear before it can conclude anything. These are declared now and recorded with today's date.",
      "classes": "Source classes",
      "classesHelp": "Every source carries its class, and classes are never mixed silently. Choose at least one.",
      "floor": "Acquisition floor",
      "floorHelp": "The share of found works that must be obtained as confirmed copies. Between 0 and 1.",
      "rationale": "Why this floor",
      "rationaleHelp": "At least 20 characters. A bar without a reason is a bar somebody can move.",
      "supplied": "Copies you supply yourself",
      "suppliedCount": "Count toward the floor once verified",
      "suppliedSeparate": "Read them, but report them separately from the floor",
      "suppliedHelp": "Declared now, before any copy exists. It cannot change under this protocol.",
      "notation": "How this field writes its figures",
      "notationCustom": "Custom list",
      "customLabels": "Notation, one per line",
      "customLabelsHelp": "For example the abbreviations a paper writes next to a number.",
      "hosts": "Hosts never to contact, besides the standing list",
      "hostsHelp": "One bare host name per line, with no scheme, path or wildcard.",
      "fixedHosts": "Always excluded: {hosts}",
      "afterSave": "Claimstone checks the classes, the floor and its reason, and keeps a draft.",
      "atCreation": "The floor {floor} is written with today's date and your reason, and it has no override. Every source will carry one of {classes} classes. Excluded hosts are never contacted ({added} added by you). Copies you supply: {supplied}.",
      "afterStart": "After the search, Claimstone counts how many of the works it found it could obtain as confirmed copies. Below the floor it reports INSUFFICIENT_ACQUISITION and produces no verdicts at all: a corpus read at 42% that certifies itself complete is worse than no corpus."
    },
    "step4": {
      "title": "4 · Review and create",
      "intro": "This is exactly what will be created. Check it, then confirm.",
      "summary": "Project {name}: {topics} topics, {total} questions ({literature} literature, {operational} operational), {classes} source classes, floor {floor}.",
      "needSteps": "Steps 1 to 3 must be saved before you can review the project.",
      "files": "The files that will be created",
      "advanced": "Advanced: edit the generated files",
      "advancedHelp": "An edit replaces a whole file and must still load with the same checks. If you change an earlier step after editing here, reset the files so they are generated again.",
      "saveFiles": "Save file changes",
      "resetFiles": "Reset to generated files",
      "confirm": "I understand that the question registry and the floor are frozen at version 1 with today's date, and that changing them later needs a dated new version.",
      "create": "Create the project",
      "creating": "Creating…",
      "startDisabled": "Start research",
      "startNote": "Not available yet: authorizing and starting research comes with the next stage of the portal.",
      "notStartedTitle": "What does not start",
      "notStarted": "Creating the project starts no search, no copy request and no model call, and spends nothing.",
      "nextTitle": "What comes next",
      "next1": "You authorize one exact plan: the searches, the copy requests and any paid model work, up to a cap you set.",
      "next2": "Claimstone searches the indexes and obtains legal copies, recording every attempt.",
      "next3": "It prepares the documents, extracts claims bound to verbatim quotes, and a different model reviews each one.",
      "next4": "It builds an evidence profile for each literature question.",
      "next5": "A person reads each profile and signs a verdict. Nothing is signed for you.",
      "afterSave": "There is nothing to save here: the draft is complete once steps 1 to 3 are saved. Creating the project is the one action on this page.",
      "atCreation": "Claimstone writes three files under projects/{name}/, freezes the question registry and the floor at version 1 dated today, and records each file's hash. It starts nothing.",
      "afterStart": "You will authorize one exact plan. Claimstone then searches, obtains legal copies, prepares the documents, extracts claims bound to verbatim quotes, has a different model review each one, and builds an evidence profile per literature question. A person reads it and signs. This stage of the portal does not do any of that yet."
    },
    "created": {
      "title": "Project created",
      "body": "{name} now exists, frozen at version 1. Nothing has started.",
      "files": "Recorded files",
      "projects": "Go to the projects",
      "another": "Start another project"
    },
    "errors": {
      "generic": "Something went wrong."
    }
  }
}
```

- [ ] **Step 4: Write `web/src/messages/it.json`** (same keys, same placeholders)

```json
{
  "shell": {
    "newProject": "+ Nuovo progetto",
    "language": "Lingua"
  },
  "wizard": {
    "title": "Nuovo progetto",
    "lede": "Descrivi un argomento, scrivi le domande, dichiara le fonti e la soglia. Claimstone controlla ogni passo e conserva una bozza. Nulla parte finché non crei il progetto, e crearlo non avvia nessuna ricerca.",
    "signIn": "Accedi per creare un progetto.",
    "signInLink": "Accedi",
    "loading": "Caricamento della bozza…",
    "back": "Indietro",
    "saveContinue": "Salva e continua",
    "saving": "Salvataggio…",
    "draftNote": "Bozza salvata · nulla parte finché non crei il progetto",
    "problems": "Correggi questi punti prima di continuare:",
    "stale": "Questa bozza è stata modificata altrove. Ricaricala per vedere l'ultima versione.",
    "reload": "Ricarica la bozza",
    "discarded": "Questa bozza è stata scartata. Non è stato creato nulla.",
    "backToDrafts": "Torna alle tue bozze",
    "rail": {
      "label": "Passi",
      "done": "completato",
      "current": "attuale"
    },
    "steps": {
      "1": { "name": "Argomento", "hint": "cosa ti serve sapere, e perché" },
      "2": { "name": "Domande", "hint": "le domande di letteratura ricevono un verdetto che firmi tu" },
      "3": { "name": "Fonti e rigore", "hint": "da dove può venire l'evidenza, e la soglia" },
      "4": { "name": "Riepilogo e creazione", "hint": "congela il protocollo" }
    },
    "explain": {
      "title": "Cosa farà Claimstone",
      "afterSave": "Dopo il salvataggio di questo passo",
      "atCreation": "Quando crei il progetto",
      "afterStart": "Dopo l'avvio della ricerca (prossima tappa)"
    },
    "drafts": {
      "title": "Le tue bozze",
      "empty": "Non hai ancora nessuna bozza.",
      "start": "Inizia un nuovo progetto",
      "resume": "Continua",
      "discard": "Scarta",
      "untitled": "Bozza senza titolo",
      "stepsSaved": "{n} passi su 3 salvati",
      "openProject": "Apri il progetto",
      "status": {
        "open": "aperta",
        "discarded": "scartata",
        "created": "creata"
      }
    },
    "kind": {
      "effect": "effect — giudicata sui risultati che la mettono alla prova: stime, incertezza, orizzonte, campione, disegno.",
      "heterogeneity": "heterogeneity — giudicata sul contrasto fra sottogruppi, con la sua incertezza e se l'analisi per sottogruppi era stata prespecificata.",
      "method": "method — giudicata su che tipo di sostegno ogni fonte dà all'affermazione metodologica.",
      "premise": "premise — giudicata sull'enunciato esplicito, o su una sua contraddizione.",
      "operational": "operational — resta nel progetto; nessun verdetto di letteratura si applica, e non compare mai come in attesa della tua firma."
    },
    "step1": {
      "title": "1 · L'argomento",
      "intro": "Dai un nome al progetto ed elenca cosa cercare. I termini sono ampi di proposito: servono a trovare opere, non a definire cosa si impara.",
      "name": "Nome del progetto",
      "nameHelp": "Da 2 a 63 lettere minuscole, cifre o trattini. Diventa il nome della cartella e non si può cambiare.",
      "description": "Cosa ti serve sapere, e perché (facoltativo)",
      "descriptionHelp": "Cosa è dentro e cosa è fuori ambito, in poche frasi. Resta con il progetto e nessuno stadio la legge.",
      "topics": "Argomenti",
      "topicLabel": "Argomento",
      "terms": "Termini di ricerca, uno per riga",
      "termsHelp": "Ogni termine viene cercato così com'è scritto.",
      "addTopic": "Aggiungi un argomento",
      "removeTopic": "Rimuovi questo argomento",
      "afterSave": "Claimstone controlla il nome e gli argomenti e conserva una bozza. Non viene creato nulla e nulla parte.",
      "atCreation": "Ogni termine di ricerca diventerà una query su ciascun indice che sceglierai più avanti. Finora: {terms} termini in {topics} argomenti, cioè {searches} ricerche per indice, o {searchesAll} se si usano tutti e tre gli indici.",
      "afterStart": "I termini trovano le opere; non definiscono cosa si impara. Allargare un argomento costa poco e da solo non può cambiare un verdetto."
    },
    "step2": {
      "title": "2 · Le domande",
      "intro": "Scrivi ogni domanda di letteratura come un'affermazione che la letteratura può sostenere o contraddire. Claimstone non giudica la tua formulazione: controlla soltanto che la domanda non sia vuota e abbia un tipo.",
      "question": "Domanda",
      "kind": "Tipo",
      "addQuestion": "Aggiungi una domanda",
      "removeQuestion": "Rimuovi questa domanda",
      "afterSave": "Claimstone controlla ogni domanda e conserva una bozza. Le domande non sono ancora congelate, quindi puoi ancora cambiarle.",
      "atCreation": "Il registro delle domande viene congelato alla versione 1, con la data di oggi. {literature} delle tue {total} domande sono di letteratura: ognuna avrà un profilo di evidenza che una persona legge e firma. {operational} sono operational: restano nel progetto, ma non ricevono mai un verdetto. Cambiare il registro più avanti è un aumento di versione datato, mai una modifica silenziosa.",
      "afterStart": "Ogni tipo è giudicato da una regola propria. Claimstone legge le fonti con queste domande in mente ed estrae affermazioni, ciascuna legata a una citazione esatta che il codice verifica."
    },
    "step3": {
      "title": "3 · Fonti e rigore",
      "intro": "Dichiara quali tipi di fonte possono contare e la soglia che un giro deve superare prima di poter concludere qualcosa. Si dichiarano ora e vengono registrati con la data di oggi.",
      "classes": "Classi di fonte",
      "classesHelp": "Ogni fonte porta la sua classe, e le classi non si mescolano mai in silenzio. Scegline almeno una.",
      "floor": "Soglia di acquisizione",
      "floorHelp": "La quota di opere trovate che deve essere ottenuta come copie confermate. Fra 0 e 1.",
      "rationale": "Perché questa soglia",
      "rationaleHelp": "Almeno 20 caratteri. Una soglia senza motivo è una soglia che qualcuno può spostare.",
      "supplied": "Copie che fornisci tu",
      "suppliedCount": "Contano per la soglia una volta verificate",
      "suppliedSeparate": "Vengono lette, ma riportate a parte rispetto alla soglia",
      "suppliedHelp": "Si dichiara ora, prima che esista una copia. Non può cambiare sotto questo protocollo.",
      "notation": "Come questo campo scrive le sue cifre",
      "notationCustom": "Elenco personalizzato",
      "customLabels": "Notazione, una per riga",
      "customLabelsHelp": "Per esempio le sigle che un articolo scrive accanto a un numero.",
      "hosts": "Host da non contattare mai, oltre all'elenco fisso",
      "hostsHelp": "Un nome di host per riga, senza schema, percorso né caratteri jolly.",
      "fixedHosts": "Sempre esclusi: {hosts}",
      "afterSave": "Claimstone controlla le classi, la soglia e il suo motivo, e conserva una bozza.",
      "atCreation": "La soglia {floor} viene scritta con la data di oggi e il tuo motivo, e non ha nessuna eccezione. Ogni fonte porterà una fra {classes} classi. Gli host esclusi non vengono mai contattati ({added} aggiunti da te). Copie che fornisci tu: {supplied}.",
      "afterStart": "Dopo la ricerca, Claimstone conta quante delle opere trovate è riuscito a ottenere come copie confermate. Sotto la soglia riporta INSUFFICIENT_ACQUISITION e non produce nessun verdetto: un corpus letto al 42% che si certifica completo è peggio di nessun corpus."
    },
    "step4": {
      "title": "4 · Riepilogo e creazione",
      "intro": "Questo è esattamente ciò che verrà creato. Controllalo, poi conferma.",
      "summary": "Progetto {name}: {topics} argomenti, {total} domande ({literature} di letteratura, {operational} operational), {classes} classi di fonte, soglia {floor}.",
      "needSteps": "I passi da 1 a 3 devono essere salvati prima di poter rivedere il progetto.",
      "files": "I file che verranno creati",
      "advanced": "Avanzate: modifica i file generati",
      "advancedHelp": "Una modifica sostituisce un file intero e deve comunque superare gli stessi controlli. Se cambi un passo precedente dopo aver modificato qui, ripristina i file perché vengano generati di nuovo.",
      "saveFiles": "Salva le modifiche ai file",
      "resetFiles": "Ripristina i file generati",
      "confirm": "So che il registro delle domande e la soglia vengono congelati alla versione 1 con la data di oggi, e che cambiarli più avanti richiede una nuova versione datata.",
      "create": "Crea il progetto",
      "creating": "Creazione…",
      "startDisabled": "Avvia la ricerca",
      "startNote": "Non ancora disponibile: autorizzare e avviare la ricerca arriva con la prossima tappa del portale.",
      "notStartedTitle": "Cosa non parte",
      "notStarted": "Creare il progetto non avvia nessuna ricerca, nessuna richiesta di copie e nessuna chiamata a un modello, e non spende nulla.",
      "nextTitle": "Cosa viene dopo",
      "next1": "Autorizzi un piano esatto: le ricerche, le richieste di copie e l'eventuale lavoro a pagamento dei modelli, fino a un tetto che stabilisci tu.",
      "next2": "Claimstone cerca negli indici e ottiene copie legali, registrando ogni tentativo.",
      "next3": "Prepara i documenti, estrae affermazioni legate a citazioni esatte, e un modello diverso rivede ciascuna.",
      "next4": "Costruisce un profilo di evidenza per ogni domanda di letteratura.",
      "next5": "Una persona legge ogni profilo e firma un verdetto. Nulla viene firmato al tuo posto.",
      "afterSave": "Qui non c'è nulla da salvare: la bozza è completa quando i passi da 1 a 3 sono salvati. Creare il progetto è l'unica azione di questa pagina.",
      "atCreation": "Claimstone scrive tre file sotto projects/{name}/, congela il registro delle domande e la soglia alla versione 1 con la data di oggi e registra l'impronta di ciascun file. Non avvia nulla.",
      "afterStart": "Autorizzerai un piano esatto. Claimstone poi cerca, ottiene copie legali, prepara i documenti, estrae affermazioni legate a citazioni esatte, fa rivedere ciascuna a un modello diverso e costruisce un profilo di evidenza per ogni domanda di letteratura. Una persona lo legge e firma. Questa tappa del portale non fa ancora nulla di tutto ciò."
    },
    "created": {
      "title": "Progetto creato",
      "body": "{name} ora esiste, congelato alla versione 1. Non è partito nulla.",
      "files": "File registrati",
      "projects": "Vai ai progetti",
      "another": "Inizia un altro progetto"
    },
    "errors": {
      "generic": "Qualcosa è andato storto."
    }
  }
}
```

- [ ] **Step 5: Run the copy and parity tests**

Run: `npx vitest run tests/wizardcopy.test.ts tests/i18n.test.tsx`
Expected: pass (both catalogs have the same keys and placeholders).

- [ ] **Step 6: Commit**

```bash
git add web/src/messages web/tests/wizardcopy.test.ts
git commit -m "web: the wizard's copy, in Italian and English

Every step explains what happens after saving, at creation and after start.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 4: Figures, problems and the breakpoint hook

Small, pure helpers the components share.

**Files:**
- Create: `web/src/components/wizard/figures.ts`, `web/src/components/wizard/problems.tsx`, `web/src/components/wizard/useWide.ts`
- Test: `web/tests/wizardhelpers.test.tsx`

- [ ] **Step 1: Write the failing tests** `web/tests/wizardhelpers.test.tsx`

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorSummary, FieldError, messageFor, problemsOf } from "@/components/wizard/problems";
import { explainParams, show } from "@/components/wizard/figures";
import { ControlError } from "@/lib/control";

afterEach(cleanup);

describe("show", () => {
  it("renders an unknown as a dash, never 0", () => {
    expect(show(null)).toBe("—");
    expect(show(undefined)).toBe("—");
    expect(show(Number.NaN)).toBe("—");
    expect(show("")).toBe("—");
    expect(show(0)).toBe("0"); // a known zero is a figure
    expect(show(12)).toBe("12");
  });
});

describe("explainParams", () => {
  it("maps figures to the placeholders the copy uses", () => {
    const params = explainParams({
      topics: 2, terms: 5, searches_per_index: 5, searches_all_indexes: 15,
      questions_total: 8, questions_literature: 7, questions_operational: 1,
      acquisition_floor: 0.8, classes: ["ACA", "WP"], excluded_hosts_added: 1, supplied_copies: "separate",
    });
    expect(params).toMatchObject({
      topics: "2", terms: "5", searches: "5", searchesAll: "15", total: "8", literature: "7",
      operational: "1", floor: "0.80", classes: "2", added: "1", supplied: "separate",
    });
  });

  it("shows a dash for what the server has not said", () => {
    const params = explainParams({});
    expect(params.floor).toBe("—");
    expect(params.classes).toBe("—");
    expect(params.terms).toBe("—");
  });
});

describe("problems", () => {
  const error = new ControlError(422, "VALIDATION", "name: bad", [
    { path: "name", message: "use lowercase" }, { path: "topics[0].terms", message: "add a term" },
  ]);

  it("reads the details of a ControlError and nothing else", () => {
    expect(problemsOf(error)).toHaveLength(2);
    expect(problemsOf(new Error("x"))).toEqual([]);
    expect(problemsOf(null)).toEqual([]);
    expect(messageFor(problemsOf(error), "name")).toBe("use lowercase");
    expect(messageFor(problemsOf(error), "other")).toBeNull();
  });

  it("FieldError shows only its own path", () => {
    render(<FieldError problems={problemsOf(error)} path="topics[0].terms" />);
    expect(screen.getByRole("alert").textContent).toBe("add a term");
  });

  it("ErrorSummary lists every problem, and a stale revision gets the reload advice", () => {
    render(<ErrorSummary error={error} />);
    expect(screen.getByText("use lowercase")).toBeTruthy();
    cleanup();
    render(<ErrorSummary error={new ControlError(409, "STALE_REVISION", "saved from revision 1")} />);
    expect(screen.getByRole("alert").textContent).toContain("changed elsewhere");
  });

  it("ErrorSummary shows nothing without an error", () => {
    const { container } = render(<ErrorSummary error={null} />);
    expect(container.textContent).toBe("");
  });
});

describe("useWide", () => {
  it("is wide when matchMedia is absent", async () => {
    const { default: probe } = await import("./support/WideProbe");
    vi.stubGlobal("matchMedia", undefined);
    render(probe());
    expect(screen.getByTestId("wide").textContent).toBe("wide");
    vi.unstubAllGlobals();
  });
});
```

Create the tiny test support file `web/tests/support/WideProbe.tsx`:

```tsx
import { useWide } from "@/components/wizard/useWide";

function Probe() {
  return <p data-testid="wide">{useWide() ? "wide" : "narrow"}</p>;
}

export default function probe() {
  return <Probe />;
}
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/wizardhelpers.test.tsx`
Expected: FAIL (modules not found).

- [ ] **Step 3: Implement**

`web/src/components/wizard/figures.ts`:

```ts
import type { Figures } from "@/lib/control";

export const DASH = "—";

/** A figure for the page: an unknown is a dash, never 0 (a known zero stays "0"). */
export function show(value: unknown): string {
  if (value === null || value === undefined) return DASH;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : DASH;
  if (typeof value === "string") return value || DASH;
  return DASH;
}

/** The placeholders of the explanation copy, from whatever figures the server has given so far. */
export function explainParams(figures: Figures, extra: Record<string, string> = {}): Record<string, string> {
  const floor = typeof figures.acquisition_floor === "number" ? figures.acquisition_floor.toFixed(2) : DASH;
  const classes = Array.isArray(figures.classes) ? String(figures.classes.length) : DASH;
  return {
    topics: show(figures.topics),
    terms: show(figures.terms),
    searches: show(figures.searches_per_index),
    searchesAll: show(figures.searches_all_indexes),
    total: show(figures.questions_total),
    literature: show(figures.questions_literature),
    operational: show(figures.questions_operational),
    floor,
    classes,
    added: show(figures.excluded_hosts_added),
    supplied: show(figures.supplied_copies),
    ...extra,
  };
}
```

`web/src/components/wizard/problems.tsx`:

```tsx
import { useEffect, useRef } from "react";
import { ControlError } from "@/lib/control";
import type { FieldProblem } from "@/lib/control";
import { useLocale } from "@/lib/i18n";

export function problemsOf(error: Error | null): FieldProblem[] {
  return error instanceof ControlError ? error.details : [];
}

export function messageFor(problems: FieldProblem[], path: string): string | null {
  const hits = problems.filter((p) => p.path === path);
  return hits.length ? hits.map((p) => p.message).join(" ") : null;
}

/** The message under one field, for the exact path the server named. */
export function FieldError({ problems, path }: { problems: FieldProblem[]; path: string }) {
  const message = messageFor(problems, path);
  return message ? (
    <p role="alert" className="text-[13px] text-destructive">
      {message}
    </p>
  ) : null;
}

/** Every problem in one place, focused when it appears so a keyboard or screen-reader user lands on it. */
export function ErrorSummary({ error }: { error: Error | null }) {
  const { t } = useLocale();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) ref.current?.focus();
  }, [error]);
  if (!error) return null;
  const problems = problemsOf(error);
  const stale = error instanceof ControlError && error.code === "STALE_REVISION";
  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="alert"
      className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm"
    >
      {stale ? <p>{t("wizard.stale")}</p> : null}
      {problems.length ? (
        <>
          <p className="font-medium">{t("wizard.problems")}</p>
          <ul className="mt-1 list-disc pl-5">
            {problems.map((p) => (
              <li key={`${p.path}:${p.message}`}>
                {p.path ? <code className="font-mono text-xs">{p.path}</code> : null}{" "}
                <span>{p.message}</span>
              </li>
            ))}
          </ul>
        </>
      ) : stale ? null : (
        <p>{error instanceof ControlError ? error.message : t("wizard.errors.generic")}</p>
      )}
    </div>
  );
}
```

`web/src/components/wizard/useWide.ts`:

```ts
import { useEffect, useState } from "react";

const QUERY = "(min-width: 900px)";

function read(): boolean {
  return typeof matchMedia === "function" ? Boolean(matchMedia(QUERY)?.matches) : true;
}

/** The portal's one breakpoint (the sidebar already turns into a top bar at 900 px). */
export function useWide(): boolean {
  const [wide, setWide] = useState(read);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const list = matchMedia(QUERY);
    const on = () => setWide(Boolean(list?.matches));
    list?.addEventListener?.("change", on);
    on();
    return () => list?.removeEventListener?.("change", on);
  }, []);
  return wide;
}
```

- [ ] **Step 4: Run to verify pass, then typecheck**

Run: `npx vitest run tests/wizardhelpers.test.tsx && npm run typecheck`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/wizard web/tests/wizardhelpers.test.tsx web/tests/support
git commit -m "web: wizard helpers — figures, field problems, the 900 px hook

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 5: The layout — rail, form column and the explanation panel

Wide: steps on the left, form in the middle, three explanation sections on the right. Narrow: the steps become a strip on top, and the three sections an accordion under the form.

**Files:**
- Create: `web/src/components/wizard/ExplainPanel.tsx`, `web/src/components/wizard/WizardShell.tsx`
- Test: `web/tests/wizardshell.test.tsx`

- [ ] **Step 1: Write the failing tests** `web/tests/wizardshell.test.tsx`

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import ExplainPanel from "@/components/wizard/ExplainPanel";
import WizardShell from "@/components/wizard/WizardShell";
import { LocaleProvider } from "@/lib/i18n";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

function media(wide: boolean) {
  vi.stubGlobal("matchMedia", () => ({ matches: wide, addEventListener() {}, removeEventListener() {} }));
}

describe("ExplainPanel", () => {
  it("wide: the three moments are plain sections, all visible, with the server's figures", () => {
    media(true);
    render(<LocaleProvider><ExplainPanel step={1} figures={{ topics: 2, terms: 5, searches_per_index: 5, searches_all_indexes: 15 }} /></LocaleProvider>);
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(3);
    expect(document.querySelectorAll("details")).toHaveLength(0);
    expect(screen.getByText(/5 terms in 2 topics/)).toBeTruthy();
    expect(screen.getByText(/15 if all three indexes are used/)).toBeTruthy();
  });

  it("narrow: the three moments are an accordion, the first one open", () => {
    media(false);
    render(<LocaleProvider><ExplainPanel step={2} figures={{}} /></LocaleProvider>);
    const panels = [...document.querySelectorAll("details")];
    expect(panels).toHaveLength(3);
    expect(panels.map((d) => d.open)).toEqual([true, false, false]);
  });

  it("an unknown figure is a dash, not 0", () => {
    media(true);
    render(<LocaleProvider><ExplainPanel step={2} figures={{}} /></LocaleProvider>);
    expect(screen.getByText(/— of your — questions/)).toBeTruthy();
    expect(screen.queryByText(/0 of your 0/)).toBeNull();
  });

  it("explains step 3 with the INSUFFICIENT_ACQUISITION token untouched", () => {
    media(true);
    render(<LocaleProvider><ExplainPanel step={3} figures={{ acquisition_floor: 0.8 }} /></LocaleProvider>);
    expect(screen.getByText(/INSUFFICIENT_ACQUISITION/)).toBeTruthy();
    expect(screen.getByText(/floor 0\.80/)).toBeTruthy();
  });
});

describe("WizardShell", () => {
  it("marks the current step and the saved ones, with words as well as marks", () => {
    media(true);
    render(
      <MemoryRouter>
        <LocaleProvider>
          <WizardShell draftId="d1" current={2} saved={[1]} explain={<p>panel</p>}>
            <p>form</p>
          </WizardShell>
        </LocaleProvider>
      </MemoryRouter>,
    );
    const rail = screen.getByRole("navigation", { name: "Steps" });
    const items = within(rail).getAllByRole("link");
    expect(items).toHaveLength(4);
    expect(items[1].getAttribute("aria-current")).toBe("step");
    expect(within(items[0]).getByText("done")).toBeTruthy();
    expect(items[0].getAttribute("href")).toBe("/new/d1/1");
    expect(screen.getByText("form")).toBeTruthy();
    expect(screen.getByText("panel")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/wizardshell.test.tsx`
Expected: FAIL (modules not found).

- [ ] **Step 3: Implement**

`web/src/components/wizard/ExplainPanel.tsx`:

```tsx
import type { Figures } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { explainParams } from "./figures";
import { useWide } from "./useWide";

const MOMENTS = ["afterSave", "atCreation", "afterStart"] as const;

// "What Claimstone will do": fixed copy from the catalog, plus figures the server computed. The
// three moments are the same text wide or narrow; only the container changes.
export default function ExplainPanel(
  { step, figures, extra = {} }: { step: 1 | 2 | 3 | 4; figures: Figures; extra?: Record<string, string> },
) {
  const { t } = useLocale();
  const wide = useWide();
  const params = explainParams(figures, extra);
  const sections = MOMENTS.map((moment) => ({
    moment,
    title: t(`wizard.explain.${moment}`),
    body: t(`wizard.step${step}.${moment}`, params),
  }));

  return (
    <div className="flex flex-col gap-3 rounded-xl bg-card p-4 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
      <h2 className="text-base font-semibold">{t("wizard.explain.title")}</h2>
      {sections.map(({ moment, title, body }, index) =>
        wide ? (
          <section key={moment} className="border-l-2 border-amber-400 pl-3">
            <h3 className="text-[13px] font-semibold">{title}</h3>
            <p className="mt-1 text-[13px] text-muted-foreground">{body}</p>
          </section>
        ) : (
          <details key={moment} open={index === 0} className="border-l-2 border-amber-400 pl-3">
            <summary className="cursor-pointer text-[13px] font-semibold">{title}</summary>
            <p className="mt-1 text-[13px] text-muted-foreground">{body}</p>
          </details>
        ),
      )}
    </div>
  );
}
```

`web/src/components/wizard/WizardShell.tsx`:

```tsx
import type { ReactNode } from "react";
import { Link } from "react-router";
import { useLocale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const STEPS = [1, 2, 3, 4] as const;

// Wide: rail | form | explanation. Narrow: the rail is a strip on top, the explanation sits under
// the form (the DOM order is already that order, so no layout trick hides or duplicates anything).
export default function WizardShell(
  { draftId, current, saved, children, explain }:
  { draftId: string; current: number; saved: number[]; children: ReactNode; explain: ReactNode },
) {
  const { t } = useLocale();
  return (
    <div className="grid gap-5 min-[900px]:grid-cols-[210px_minmax(0,1fr)_320px]">
      <nav aria-label={t("wizard.rail.label")}>
        <ol className="flex gap-2 overflow-x-auto min-[900px]:flex-col min-[900px]:overflow-visible">
          {STEPS.map((n) => {
            const done = saved.includes(n);
            const active = n === current;
            return (
              <li key={n} className="min-w-[8.5rem] min-[900px]:min-w-0">
                <Link
                  to={`/new/${encodeURIComponent(draftId)}/${n}`}
                  aria-current={active ? "step" : undefined}
                  className={cn(
                    "flex min-h-11 flex-col justify-center rounded-lg px-3 py-1.5 text-sm ring-1",
                    active
                      ? "bg-rail text-rail-foreground ring-rail"
                      : "bg-card ring-gray-200 hover:bg-muted dark:ring-gray-800",
                  )}
                >
                  <span className="flex items-baseline gap-2 font-medium">
                    <span className="font-mono text-xs">{n}</span>
                    {t(`wizard.steps.${n}.name`)}
                    {done ? <span className="ml-auto text-xs">✓ <span className="sr-only">{t("wizard.rail.done")}</span></span> : null}
                  </span>
                  <span className={cn("hidden text-xs min-[900px]:block", active ? "text-rail-muted" : "text-muted-foreground")}>
                    {t(`wizard.steps.${n}.hint`)}
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      </nav>
      <div className="flex min-w-0 flex-col gap-4">{children}</div>
      <aside className="min-w-0 min-[900px]:sticky min-[900px]:top-4 min-[900px]:self-start">{explain}</aside>
    </div>
  );
}
```

Note: the `done` word is `sr-only` text inside the link, so `within(items[0]).getByText("done")` finds it.

- [ ] **Step 4: Run to verify pass, then typecheck**

Run: `npx vitest run tests/wizardshell.test.tsx && npm run typecheck`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/wizard/ExplainPanel.tsx web/src/components/wizard/WizardShell.tsx web/tests/wizardshell.test.tsx
git commit -m "web: wizard layout with the explanation panel (accordion under 900 px)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 6: Steps 1 and 2 — topic and questions

Both share the same contract: `{ draftId, draft, onSaved }`. A save sends the draft's current revision; the server's normalized answer and figures come back.

**Files:**
- Create: `web/src/components/wizard/StepTopic.tsx`, `web/src/components/wizard/StepQuestions.tsx`, `web/src/components/wizard/stepTypes.ts`
- Test: `web/tests/wizardsteps12.test.tsx`

- [ ] **Step 1: Write the failing tests** `web/tests/wizardsteps12.test.tsx`

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StepQuestions from "@/components/wizard/StepQuestions";
import StepTopic from "@/components/wizard/StepTopic";
import { setCsrfToken } from "@/lib/control";
import type { DraftState } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";

const draft = (steps: DraftState["steps"] = {}): DraftState => ({
  draft_id: "d1", revision: 3, status: "open", steps, advanced: {}, figures: {}, project: null,
  last_failure: null, started_at: "t", updated_at: "t",
});

let calls: Array<{ url: string; body: unknown }>;
function mockFetch(status: number, body: unknown) {
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    return Promise.resolve(new Response(JSON.stringify(body), {
      status, headers: { "Content-Type": "application/json" },
    }));
  });
}

beforeEach(() => setCsrfToken("tok"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

const wrap = (node: JSX.Element) => render(<LocaleProvider>{node}</LocaleProvider>);

describe("StepTopic", () => {
  it("sends the trimmed terms and the draft's revision, then reports the figures", async () => {
    mockFetch(200, { revision: 4, data: {}, figures: { topics: 1, terms: 2 } });
    const onSaved = vi.fn();
    wrap(<StepTopic draftId="d1" draft={draft()} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText(/Project name/), { target: { value: "news-tone" } });
    fireEvent.change(screen.getByLabelText(/^Topic/), { target: { value: "News" } });
    fireEvent.change(screen.getByLabelText(/Search terms/), { target: { value: "a b\n\n  c d  \n" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(calls[0].url).toBe("/control/v1/new/d1/steps/1");
    expect(calls[0].body).toEqual({ base_revision: 3, data: {
      name: "news-tone", description: "", topics: [{ label: "News", terms: ["a b", "c d"] }] } });
    expect(onSaved).toHaveBeenCalledWith({ step: 1, revision: 4, figures: { topics: 1, terms: 2 } });
  });

  it("shows the server's field error under the field and keeps what was typed", async () => {
    mockFetch(422, { error: { code: "VALIDATION", message: "name: bad", details: [
      { path: "name", message: "use lowercase letters" }] } });
    const onSaved = vi.fn();
    wrap(<StepTopic draftId="d1" draft={draft()} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText(/Project name/), { target: { value: "Bad Name" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(screen.getAllByText("use lowercase letters").length).toBeGreaterThan(0));
    expect(onSaved).not.toHaveBeenCalled();
    expect((screen.getByLabelText(/Project name/) as HTMLInputElement).value).toBe("Bad Name");
  });

  it("starts from the saved draft, ids included, and can add and remove topics", () => {
    const saved = { "1": { revision: 2, data: { name: "news-tone", description: "scope",
      topics: [{ id: "T01", label: "News", terms: ["a", "b"] }] } } };
    wrap(<StepTopic draftId="d1" draft={draft(saved)} onSaved={vi.fn()} />);
    expect((screen.getByLabelText(/Project name/) as HTMLInputElement).value).toBe("news-tone");
    expect((screen.getByLabelText(/Search terms/) as HTMLTextAreaElement).value).toBe("a\nb");
    fireEvent.click(screen.getByRole("button", { name: "Add a topic" }));
    expect(screen.getAllByLabelText(/Search terms/)).toHaveLength(2);
    fireEvent.click(screen.getAllByRole("button", { name: "Remove this topic" })[1]);
    expect(screen.getAllByLabelText(/Search terms/)).toHaveLength(1);
  });
});

describe("StepQuestions", () => {
  it("sends text and kind, never a default kind, and glosses the chosen kind", async () => {
    mockFetch(200, { revision: 5, data: {}, figures: { questions_total: 1 } });
    const onSaved = vi.fn();
    wrap(<StepQuestions draftId="d1" draft={draft()} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText(/^Question/), { target: { value: "Does it work?" } });
    expect((screen.getByLabelText("Kind") as HTMLSelectElement).value).toBe("");
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "operational" } });
    expect(screen.getByText(/no literature verdict applies/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(calls[0].body).toEqual({ base_revision: 3, data: {
      questions: [{ text: "Does it work?", kind: "operational" }] } });
  });

  it("the server's refusal of an empty kind appears under the question", async () => {
    mockFetch(422, { error: { code: "VALIDATION", message: "x", details: [
      { path: "questions[0].kind", message: "choose one of effect, heterogeneity" }] } });
    wrap(<StepQuestions draftId="d1" draft={draft()} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/^Question/), { target: { value: "x?" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(screen.getAllByText(/choose one of effect/).length).toBeGreaterThan(0));
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/wizardsteps12.test.tsx`
Expected: FAIL (modules not found).

- [ ] **Step 3: Implement**

`web/src/components/wizard/stepTypes.ts`:

```ts
import type { DraftState, Figures } from "@/lib/control";

export interface Saved {
  step: number;
  revision: number;
  figures: Figures;
}

export interface StepProps {
  draftId: string;
  draft: DraftState;
  onSaved: (saved: Saved) => void;
}

export const inputClass = "min-h-11 rounded-lg border border-border bg-card px-3 text-sm font-normal";
export const areaClass = "min-h-24 rounded-lg border border-border bg-card px-3 py-2 text-sm font-normal";
export const primaryClass = "min-h-11 rounded-lg bg-rail px-4 text-sm font-semibold text-rail-foreground disabled:opacity-50";
export const quietClass = "min-h-11 rounded-lg border border-border px-3 text-sm";
export const cardClass = "rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800";
```

`web/src/components/wizard/StepTopic.tsx`:

```tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { ErrorSummary, FieldError, problemsOf } from "./problems";
import { areaClass, cardClass, inputClass, primaryClass, quietClass } from "./stepTypes";
import type { StepProps } from "./stepTypes";

interface TopicRow {
  id?: string;
  label: string;
  terms: string;
}

interface SavedTopic {
  name?: string;
  description?: string;
  topics?: Array<{ id: string; label: string; terms: string[] }>;
}

export default function StepTopic({ draftId, draft, onSaved }: StepProps) {
  const { t } = useLocale();
  const saved = draft.steps["1"]?.data as SavedTopic | undefined;
  const [name, setName] = useState(saved?.name ?? "");
  const [description, setDescription] = useState(saved?.description ?? "");
  const [topics, setTopics] = useState<TopicRow[]>(
    saved?.topics?.map((x) => ({ id: x.id, label: x.label, terms: x.terms.join("\n") }))
      ?? [{ label: "", terms: "" }],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const problems = problemsOf(error);

  const update = (index: number, patch: Partial<TopicRow>) =>
    setTopics((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  async function submit(event: FormEvent) {
    event.preventDefault(); // the CSP has form-action 'none': a native submit is never wanted
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = {
        name: name.trim(),
        description,
        topics: topics.map((row) => ({
          ...(row.id ? { id: row.id } : {}),
          label: row.label,
          terms: row.terms.split("\n").map((s) => s.trim()).filter(Boolean),
        })),
      };
      const result = await control.newSaveStep(draftId, 1, draft.revision, data);
      onSaved({ step: 1, revision: result.revision, figures: result.figures });
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <section className={cardClass}>
        <h2 className="text-base font-semibold">{t("wizard.step1.title")}</h2>
        <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">{t("wizard.step1.intro")}</p>
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("wizard.step1.name")}
            <input value={name} onChange={(e) => setName(e.target.value)} className={`${inputClass} font-mono`} />
            <span className="text-[13px] font-normal text-muted-foreground">{t("wizard.step1.nameHelp")}</span>
          </label>
          <FieldError problems={problems} path="name" />
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("wizard.step1.description")}
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} className={areaClass} />
            <span className="text-[13px] font-normal text-muted-foreground">{t("wizard.step1.descriptionHelp")}</span>
          </label>
          <FieldError problems={problems} path="description" />
        </div>
      </section>

      <section className={cardClass}>
        <h2 className="text-base font-semibold">{t("wizard.step1.topics")}</h2>
        <FieldError problems={problems} path="topics" />
        <div className="mt-3 flex flex-col gap-4">
          {topics.map((row, index) => (
            <fieldset key={row.id ?? `new-${index}`} className="flex flex-col gap-2 rounded-lg border border-border p-3">
              <label className="flex flex-col gap-1 text-sm font-medium">
                {t("wizard.step1.topicLabel")}
                <input value={row.label} onChange={(e) => update(index, { label: e.target.value })} className={inputClass} />
              </label>
              <FieldError problems={problems} path={`topics[${index}].label`} />
              <label className="flex flex-col gap-1 text-sm font-medium">
                {t("wizard.step1.terms")}
                <textarea value={row.terms} onChange={(e) => update(index, { terms: e.target.value })} className={`${areaClass} font-mono`} />
                <span className="text-[13px] font-normal text-muted-foreground">{t("wizard.step1.termsHelp")}</span>
              </label>
              <FieldError problems={problems} path={`topics[${index}].terms`} />
              <div>
                <button
                  type="button"
                  disabled={topics.length === 1}
                  onClick={() => setTopics((rows) => rows.filter((_, i) => i !== index))}
                  className={quietClass}
                >
                  {t("wizard.step1.removeTopic")}
                </button>
              </div>
            </fieldset>
          ))}
        </div>
        <button type="button" onClick={() => setTopics((rows) => [...rows, { label: "", terms: "" }])} className={`${quietClass} mt-3`}>
          {t("wizard.step1.addTopic")}
        </button>
      </section>

      <ErrorSummary error={error} />
      <div className="flex items-center gap-3">
        <button type="submit" disabled={busy} className={primaryClass}>
          {busy ? t("wizard.saving") : t("wizard.saveContinue")}
        </button>
        <span className="text-[13px] text-muted-foreground">{t("wizard.draftNote")}</span>
      </div>
    </form>
  );
}
```

`web/src/components/wizard/StepQuestions.tsx`:

```tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { control } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { ErrorSummary, FieldError, problemsOf } from "./problems";
import { areaClass, cardClass, inputClass, primaryClass, quietClass } from "./stepTypes";
import type { StepProps } from "./stepTypes";

// The engine's kinds, as the engine spells them. They stay canonical on screen; the gloss is beside.
const KINDS = ["effect", "heterogeneity", "method", "premise", "operational"] as const;

interface QuestionRow {
  id?: string;
  text: string;
  kind: string;
}

export default function StepQuestions({ draftId, draft, onSaved }: StepProps) {
  const { t } = useLocale();
  const saved = draft.steps["2"]?.data as { questions?: QuestionRow[] } | undefined;
  const [rows, setRows] = useState<QuestionRow[]>(saved?.questions ?? [{ text: "", kind: "" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const problems = problemsOf(error);

  const update = (index: number, patch: Partial<QuestionRow>) =>
    setRows((list) => list.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = { questions: rows.map((row) => ({ ...(row.id ? { id: row.id } : {}), text: row.text, kind: row.kind })) };
      const result = await control.newSaveStep(draftId, 2, draft.revision, data);
      onSaved({ step: 2, revision: result.revision, figures: result.figures });
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <section className={cardClass}>
        <h2 className="text-base font-semibold">{t("wizard.step2.title")}</h2>
        <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">{t("wizard.step2.intro")}</p>
        <FieldError problems={problems} path="questions" />
        <div className="flex flex-col gap-4">
          {rows.map((row, index) => (
            <fieldset key={row.id ?? `new-${index}`} className="flex flex-col gap-2 rounded-lg border border-border p-3">
              <label className="flex flex-col gap-1 text-sm font-medium">
                {t("wizard.step2.question")}
                <textarea value={row.text} onChange={(e) => update(index, { text: e.target.value })} className={areaClass} />
              </label>
              <FieldError problems={problems} path={`questions[${index}].text`} />
              <label className="flex flex-col gap-1 text-sm font-medium">
                {t("wizard.step2.kind")}
                <select
                  value={row.kind}
                  onChange={(e) => update(index, { kind: e.target.value })}
                  className={`${inputClass} font-mono`}
                >
                  <option value="" />
                  {KINDS.map((kind) => (
                    <option key={kind} value={kind}>{kind}</option>
                  ))}
                </select>
              </label>
              {row.kind ? (
                <p className="text-[13px] text-muted-foreground">{t(`wizard.kind.${row.kind}`)}</p>
              ) : null}
              <FieldError problems={problems} path={`questions[${index}].kind`} />
              <div>
                <button
                  type="button"
                  disabled={rows.length === 1}
                  onClick={() => setRows((list) => list.filter((_, i) => i !== index))}
                  className={quietClass}
                >
                  {t("wizard.step2.removeQuestion")}
                </button>
              </div>
            </fieldset>
          ))}
        </div>
        <button type="button" onClick={() => setRows((list) => [...list, { text: "", kind: "" }])} className={`${quietClass} mt-3`}>
          {t("wizard.step2.addQuestion")}
        </button>
      </section>

      <ErrorSummary error={error} />
      <div className="flex items-center gap-3">
        <button type="submit" disabled={busy} className={primaryClass}>
          {busy ? t("wizard.saving") : t("wizard.saveContinue")}
        </button>
        <span className="text-[13px] text-muted-foreground">{t("wizard.draftNote")}</span>
      </div>
    </form>
  );
}
```

Note on the test `screen.getByLabelText("Kind")`: the label text is "Kind" wrapping the select; `getByLabelText("Kind")` matches the label whose text content is exactly "Kind" plus the select's option text? A wrapping label's text includes the options' text ("effect heterogeneity …"), so an exact-string match fails. Use a regex in the test instead: replace `screen.getByLabelText("Kind")` with `screen.getByLabelText(/^Kind/)` in the two places before running Step 4.

- [ ] **Step 4: Fix the label matchers, run, typecheck**

In `web/tests/wizardsteps12.test.tsx` replace both `getByLabelText("Kind")` with `getByLabelText(/^Kind/)`.

Run: `npx vitest run tests/wizardsteps12.test.tsx && npm run typecheck`
Expected: pass. If `getByLabelText(/^Topic/)` matches both "Topic" (field) and "Topics" heading-free labels, tighten to `/^Topic\b/`.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/wizard web/tests/wizardsteps12.test.tsx
git commit -m "web: wizard steps 1 and 2 — topic and questions

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 7: Step 3 — sources and rigour

Reads the template (`control.newTemplate("general")`) for the class list and notation presets. Nothing defaults silently: no class is pre-ticked and the supplied-copies choice starts empty, because both are declarations.

**Files:**
- Create: `web/src/components/wizard/StepSources.tsx`
- Test: `web/tests/wizardstep3.test.tsx`

- [ ] **Step 1: Write the failing tests** `web/tests/wizardstep3.test.tsx`

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StepSources from "@/components/wizard/StepSources";
import { setCsrfToken } from "@/lib/control";
import type { DraftState } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";

const template = {
  id: "general", label: "General", default_floor: 0.8,
  classes: [
    { id: "ACA", name: "peer-reviewed academic", weight_hint: "highest", notes: "version of record" },
    { id: "WP", name: "working paper", weight_hint: "high", notes: "not refereed" },
  ],
  excluded_hosts: ["sci-hub.se", "libgen.is"],
  notation_presets: [{ id: "none", label: "No special notation" }, { id: "health", label: "Health" }],
};
const draft: DraftState = {
  draft_id: "d1", revision: 4, status: "open", steps: {}, advanced: {}, figures: {}, project: null,
  last_failure: null, started_at: "t", updated_at: "t",
};

let calls: Array<{ url: string; body: unknown }>;
beforeEach(() => {
  setCsrfToken("tok");
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    const body = url.includes("/new-templates/") ? template : { revision: 5, data: {}, figures: { classes: ["ACA"] } };
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

const mount = (onSaved = vi.fn()) => {
  render(<LocaleProvider><StepSources draftId="d1" draft={draft} onSaved={onSaved} /></LocaleProvider>);
  return onSaved;
};

describe("StepSources", () => {
  it("lists the template's classes with their ids, ticks none, and shows the fixed hosts", async () => {
    mount();
    expect(await screen.findByLabelText(/ACA/)).toBeTruthy();
    expect((screen.getByLabelText(/ACA/) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText(/Always excluded: sci-hub.se, libgen.is/)).toBeTruthy();
    expect((screen.getByLabelText(/^Acquisition floor/) as HTMLInputElement).value).toBe("0.80");
    expect((screen.getByLabelText(/Count toward the floor/) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText(/Read them, but report them separately/) as HTMLInputElement).checked).toBe(false);
  });

  it("sends the declarations exactly as chosen", async () => {
    const onSaved = mount();
    fireEvent.click(await screen.findByLabelText(/ACA/));
    fireEvent.change(screen.getByLabelText(/^Acquisition floor/), { target: { value: "0.9" } });
    fireEvent.change(screen.getByLabelText(/Why this floor/), { target: { value: "Set before the first measured round." } });
    fireEvent.click(screen.getByLabelText(/Read them, but report them separately/));
    fireEvent.change(screen.getByLabelText(/Hosts never to contact/), { target: { value: "example.org\n\n" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const post = calls.find((c) => c.url.endsWith("/steps/3"))!;
    expect(post.body).toEqual({ base_revision: 4, data: {
      template: "general", classes: ["ACA"], acquisition_floor: 0.9,
      floor_rationale: "Set before the first measured round.", supplied_copies: "separate",
      notation: "none", custom_value_labels: [], extra_excluded_hosts: ["example.org"] } });
  });

  it("a custom notation sends its own list", async () => {
    mount();
    await screen.findByLabelText(/ACA/);
    fireEvent.change(screen.getByLabelText(/How this field writes/), { target: { value: "custom" } });
    fireEvent.change(await screen.findByLabelText(/Notation, one per line/), { target: { value: "Sharpe\nalpha" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/steps/3"))).toBe(true));
    const data = (calls.find((c) => c.url.endsWith("/steps/3"))!.body as { data: Record<string, unknown> }).data;
    expect(data.notation).toBe("custom");
    expect(data.custom_value_labels).toEqual(["Sharpe", "alpha"]);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/wizardstep3.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement** `web/src/components/wizard/StepSources.tsx`

```tsx
import { useState } from "react";
import type { FormEvent } from "react";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { WizardTemplate } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { ErrorSummary, FieldError, problemsOf } from "./problems";
import { areaClass, cardClass, inputClass, primaryClass } from "./stepTypes";
import type { StepProps } from "./stepTypes";

const TEMPLATE = "general";

interface SavedSources {
  classes?: string[];
  acquisition_floor?: number;
  floor_rationale?: string;
  supplied_copies?: string;
  notation?: string;
  value_labels?: string[];
  extra_excluded_hosts?: string[];
}

export default function StepSources(props: StepProps) {
  const template = useApi(() => control.newTemplate(TEMPLATE), []);
  if (template.error) return <ErrorState error={template.error} context="template" />;
  if (template.pending || !template.data) return <Pending label="…" />;
  return <SourcesForm {...props} template={template.data} />;
}

function SourcesForm({ draftId, draft, onSaved, template }: StepProps & { template: WizardTemplate }) {
  const { t } = useLocale();
  const saved = draft.steps["3"]?.data as SavedSources | undefined;
  const [classes, setClasses] = useState<string[]>(saved?.classes ?? []);
  const [floor, setFloor] = useState(String(saved?.acquisition_floor ?? template.default_floor.toFixed(2)));
  const [rationale, setRationale] = useState(saved?.floor_rationale ?? "");
  const [supplied, setSupplied] = useState(saved?.supplied_copies ?? "");
  const [notation, setNotation] = useState(saved?.notation ?? "none");
  const [custom, setCustom] = useState(notation === "custom" ? (saved?.value_labels ?? []).join("\n") : "");
  const [hosts, setHosts] = useState((saved?.extra_excluded_hosts ?? []).join("\n"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const problems = problemsOf(error);
  const lines = (text: string) => text.split("\n").map((s) => s.trim()).filter(Boolean);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = {
        template: template.id,
        classes,
        acquisition_floor: Number(floor),
        floor_rationale: rationale,
        supplied_copies: supplied,
        notation,
        custom_value_labels: notation === "custom" ? lines(custom) : [],
        extra_excluded_hosts: lines(hosts),
      };
      const result = await control.newSaveStep(draftId, 3, draft.revision, data);
      onSaved({ step: 3, revision: result.revision, figures: result.figures });
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  const toggle = (id: string) =>
    setClasses((held) => (held.includes(id) ? held.filter((x) => x !== id) : [...held, id]));

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <section className={cardClass}>
        <h2 className="text-base font-semibold">{t("wizard.step3.title")}</h2>
        <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">{t("wizard.step3.intro")}</p>

        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium">{t("wizard.step3.classes")}</legend>
          <p className="text-[13px] text-muted-foreground">{t("wizard.step3.classesHelp")}</p>
          {template.classes.map((c) => (
            <label key={c.id} className="flex items-start gap-2 rounded-lg border border-border p-2 text-sm">
              <input type="checkbox" checked={classes.includes(c.id)} onChange={() => toggle(c.id)} className="mt-1" />
              <span>
                <span className="font-mono text-xs">{c.id}</span> {c.name}
                <span className="block text-[13px] text-muted-foreground">{c.notes}</span>
              </span>
            </label>
          ))}
          <FieldError problems={problems} path="classes" />
        </fieldset>

        <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,160px)_minmax(0,1fr)]">
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("wizard.step3.floor")}
            <input value={floor} onChange={(e) => setFloor(e.target.value)} inputMode="decimal" className={`${inputClass} font-mono`} />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("wizard.step3.rationale")}
            <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} className={areaClass} />
          </label>
        </div>
        <p className="mt-1 text-[13px] text-muted-foreground">{t("wizard.step3.floorHelp")} {t("wizard.step3.rationaleHelp")}</p>
        <FieldError problems={problems} path="acquisition_floor" />
        <FieldError problems={problems} path="floor_rationale" />

        <fieldset className="mt-4 flex flex-col gap-2">
          <legend className="text-sm font-medium">{t("wizard.step3.supplied")}</legend>
          {(["count", "separate"] as const).map((value) => (
            <label key={value} className="flex items-center gap-2 text-sm">
              <input type="radio" name="supplied" checked={supplied === value} onChange={() => setSupplied(value)} />
              {value === "count" ? t("wizard.step3.suppliedCount") : t("wizard.step3.suppliedSeparate")}
            </label>
          ))}
          <p className="text-[13px] text-muted-foreground">{t("wizard.step3.suppliedHelp")}</p>
          <FieldError problems={problems} path="supplied_copies" />
        </fieldset>

        <div className="mt-4 flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("wizard.step3.notation")}
            <select value={notation} onChange={(e) => setNotation(e.target.value)} className={inputClass}>
              {template.notation_presets.map((p) => (
                <option key={p.id} value={p.id}>{p.label}</option>
              ))}
              <option value="custom">{t("wizard.step3.notationCustom")}</option>
            </select>
          </label>
          <FieldError problems={problems} path="notation" />
          {notation === "custom" ? (
            <label className="flex flex-col gap-1 text-sm font-medium">
              {t("wizard.step3.customLabels")}
              <textarea value={custom} onChange={(e) => setCustom(e.target.value)} className={`${areaClass} font-mono`} />
              <span className="text-[13px] font-normal text-muted-foreground">{t("wizard.step3.customLabelsHelp")}</span>
            </label>
          ) : null}
        </div>

        <div className="mt-4 flex flex-col gap-1">
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("wizard.step3.hosts")}
            <textarea value={hosts} onChange={(e) => setHosts(e.target.value)} className={`${areaClass} font-mono`} />
            <span className="text-[13px] font-normal text-muted-foreground">{t("wizard.step3.hostsHelp")}</span>
          </label>
          <p className="text-[13px] text-muted-foreground">
            {t("wizard.step3.fixedHosts", { hosts: template.excluded_hosts.join(", ") })}
          </p>
        </div>
      </section>

      <ErrorSummary error={error} />
      <div className="flex items-center gap-3">
        <button type="submit" disabled={busy} className={primaryClass}>
          {busy ? t("wizard.saving") : t("wizard.saveContinue")}
        </button>
        <span className="text-[13px] text-muted-foreground">{t("wizard.draftNote")}</span>
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Run to verify pass, then typecheck**

Run: `npx vitest run tests/wizardstep3.test.tsx && npm run typecheck`
Expected: pass. (If `getByLabelText(/ACA/)` matches more than one label, make the class label text `ACA — name` unique by wrapping the id in the checkbox's `aria-label={c.id}`; keep the visible text.)

- [ ] **Step 5: Commit**

```bash
git add web/src/components/wizard/StepSources.tsx web/tests/wizardstep3.test.tsx
git commit -m "web: wizard step 3 — sources and rigour (nothing defaulted silently)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 8: Step 4 — review, Advanced, create

The review shows the server's preview (the files and figures that will actually be created), the Advanced editor, the confirmation and the disabled "Start research" button with its reason. Creation needs the literal confirmation and sends nothing else anywhere.

**Files:**
- Create: `web/src/components/wizard/StepReview.tsx`
- Test: `web/tests/wizardstep4.test.tsx`

- [ ] **Step 1: Write the failing tests** `web/tests/wizardstep4.test.tsx`

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StepReview from "@/components/wizard/StepReview";
import { setCsrfToken } from "@/lib/control";
import type { DraftState } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";

const step = (data: Record<string, unknown>) => ({ data, revision: 2 });
const full = (): DraftState => ({
  draft_id: "d1", revision: 6, status: "open",
  steps: { "1": step({ name: "news-tone" }), "2": step({}), "3": step({}) },
  advanced: { "sources.yaml": "OLD" }, figures: {}, project: null, last_failure: null,
  started_at: "t", updated_at: "t",
});

const preview = {
  figures: { topics: 1, terms: 2, questions_total: 2, questions_literature: 1, questions_operational: 1,
             classes: ["ACA"], acquisition_floor: 0.8 },
  protocol_sha256: "a".repeat(64), revision: 6,
  files: { "topics.yaml": "T", "questions.yaml": "Q", "sources.yaml": "S" },
};

let calls: Array<{ method: string; url: string; body: unknown }>;
let createStatus = 201;
beforeEach(() => {
  setCsrfToken("tok");
  calls = [];
  createStatus = 201;
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : null });
    let body: unknown = preview;
    let status = 200;
    if (url.endsWith("/create")) {
      status = createStatus;
      body = createStatus === 201
        ? { project: "news-tone", protocol_sha256: "b".repeat(64), files: { "topics.yaml": "h" },
            frozen: { registry_version: 1, frozen_at: "2026-10-10", floor_version: 1 } }
        : { error: { code: "NAME_TAKEN", message: "a project named news-tone already exists" } };
    }
    if (url.endsWith("/advanced")) body = { revision: 7 };
    return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

const mount = (draft = full(), handlers: Partial<{ onCreated: () => void; onChanged: () => void }> = {}) =>
  render(
    <MemoryRouter>
      <LocaleProvider>
        <StepReview draftId="d1" draft={draft} onCreated={handlers.onCreated ?? vi.fn()} onChanged={handlers.onChanged ?? vi.fn()} />
      </LocaleProvider>
    </MemoryRouter>,
  );

describe("StepReview", () => {
  it("asks for steps 1 to 3 first when they are not all saved", () => {
    const draft = { ...full(), steps: { "1": step({}) } };
    mount(draft);
    expect(screen.getByText(/Steps 1 to 3 must be saved/)).toBeTruthy();
    expect(calls).toHaveLength(0);
  });

  it("shows the summary from the server's preview, and the files", async () => {
    mount();
    expect(await screen.findByText(/Project news-tone: 1 topics, 2 questions \(1 literature, 1 operational\)/)).toBeTruthy();
    expect(screen.getByText("topics.yaml")).toBeTruthy();
  });

  it("Create needs the confirmation, and Start research is disabled with its reason", async () => {
    mount();
    const create = (await screen.findByRole("button", { name: "Create the project" })) as HTMLButtonElement;
    expect(create.disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Start research" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Not available yet/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/I understand that the question registry/));
    expect(create.disabled).toBe(false);
  });

  it("creates, reports the result, and sends only the one create request", async () => {
    const onCreated = vi.fn();
    mount(full(), { onCreated });
    fireEvent.click(await screen.findByLabelText(/I understand that the question registry/));
    fireEvent.click(screen.getByRole("button", { name: "Create the project" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    const writes = calls.filter((c) => c.method !== "GET");
    expect(writes.map((c) => c.url)).toEqual(["/control/v1/new/d1/create"]);
    expect(writes[0].body).toEqual({ confirm: true });
    expect(onCreated.mock.calls[0][0].project).toBe("news-tone");
  });

  it("shows the server's refusal when the name was taken meanwhile", async () => {
    createStatus = 409;
    mount();
    fireEvent.click(await screen.findByLabelText(/I understand that the question registry/));
    fireEvent.click(screen.getByRole("button", { name: "Create the project" }));
    expect(await screen.findByText(/already exists/)).toBeTruthy();
  });

  it("Advanced sends only the changed files, keeping earlier overrides", async () => {
    const onChanged = vi.fn();
    mount(full(), { onChanged });
    await screen.findByText("sources.yaml");
    fireEvent.click(screen.getByText("Advanced: edit the generated files"));
    fireEvent.change(screen.getByLabelText("topics.yaml"), { target: { value: "T2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save file changes" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const post = calls.find((c) => c.url.endsWith("/advanced"))!;
    expect(post.body).toEqual({ base_revision: 6, files: { "sources.yaml": "OLD", "topics.yaml": "T2" } });
  });

  it("Reset sends an empty override", async () => {
    mount();
    await screen.findByText("sources.yaml");
    fireEvent.click(screen.getByText("Advanced: edit the generated files"));
    fireEvent.click(screen.getByRole("button", { name: "Reset to generated files" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/advanced"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/advanced"))!.body).toEqual({ base_revision: 6, files: {} });
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/wizardstep4.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement** `web/src/components/wizard/StepReview.tsx`

```tsx
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { Created, DraftState, Preview } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { ErrorSummary } from "./problems";
import { explainParams } from "./figures";
import { areaClass, cardClass, primaryClass, quietClass } from "./stepTypes";

const FILES = ["topics.yaml", "questions.yaml", "sources.yaml"] as const;

export interface ReviewProps {
  draftId: string;
  draft: DraftState;
  /** Called with the creation result; the page then shows the created screen. */
  onCreated: (created: Created) => void;
  /** Called after an Advanced save or reset, so the page reloads the draft's revision. */
  onChanged: () => void;
  /** Reports the preview's figures so the explanation panel can quote them. */
  onFigures?: (figures: Preview["figures"]) => void;
}

export default function StepReview(props: ReviewProps) {
  const { t } = useLocale();
  const missing = ["1", "2", "3"].filter((n) => !props.draft.steps[n]);
  if (missing.length) {
    return (
      <section className={cardClass}>
        <h2 className="text-base font-semibold">{t("wizard.step4.title")}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{t("wizard.step4.needSteps")}</p>
        <ul className="mt-2 flex gap-2">
          {missing.map((n) => (
            <li key={n}>
              <Link className="underline" to={`/new/${encodeURIComponent(props.draftId)}/${n}`}>
                {t(`wizard.steps.${n}.name`)}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    );
  }
  return <ReviewForm {...props} />;
}

function ReviewForm({ draftId, draft, onCreated, onChanged, onFigures }: ReviewProps) {
  const { t } = useLocale();
  const preview = useApi(() => control.newPreview(draftId), [draftId, draft.revision]);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState<"create" | "files" | null>(null);
  const [error, setError] = useState<Error | null>(null);

  // Tell the page what the server computed, so the explanation panel can quote it. An effect, not a
  // call during render: setting the parent's state while rendering a child is a React error.
  useEffect(() => {
    if (preview.data) onFigures?.(preview.data.figures);
  }, [preview.data, onFigures]);

  if (preview.error) return <ErrorState error={preview.error} context="preview" />;
  if (preview.pending || !preview.data) return <Pending label={t("wizard.loading")} />;
  const data = preview.data;
  const name = String((draft.steps["1"].data as { name?: string }).name ?? "");
  const params = explainParams(data.figures, { name });

  async function run(kind: "create" | "files", work: () => Promise<void>) {
    if (busy) return;
    setBusy(kind);
    setError(null);
    try {
      await work();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(null);
    }
  }

  const create = (event: FormEvent) => {
    event.preventDefault(); // the CSP has form-action 'none'
    if (!confirmed) return;
    void run("create", async () => onCreated(await control.newCreate(draftId)));
  };

  const saveFiles = () =>
    run("files", async () => {
      const changed = Object.fromEntries(
        Object.entries(edits).filter(([file, text]) => text !== data.files[file]),
      );
      await control.newSaveAdvanced(draftId, draft.revision, { ...draft.advanced, ...changed });
      setEdits({});
      onChanged();
    });

  const resetFiles = () =>
    run("files", async () => {
      await control.newSaveAdvanced(draftId, draft.revision, {});
      setEdits({});
      onChanged();
    });

  return (
    <form onSubmit={create} className="flex flex-col gap-4">
      <section className={cardClass}>
        <h2 className="text-base font-semibold">{t("wizard.step4.title")}</h2>
        <p className="mb-3 mt-0.5 text-[13px] text-muted-foreground">{t("wizard.step4.intro")}</p>
        <p className="text-sm">{t("wizard.step4.summary", params)}</p>
        <h3 className="mt-4 text-sm font-semibold">{t("wizard.step4.files")}</h3>
        <ul className="mt-1 list-disc pl-5 font-mono text-xs">
          {FILES.map((file) => (
            <li key={file}>{file}</li>
          ))}
        </ul>
        <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{data.protocol_sha256}</p>

        <details className="mt-4 rounded-lg border border-border p-3">
          <summary className="cursor-pointer text-sm font-medium">{t("wizard.step4.advanced")}</summary>
          <p className="my-2 text-[13px] text-muted-foreground">{t("wizard.step4.advancedHelp")}</p>
          {FILES.map((file) => (
            <label key={file} className="mb-3 flex flex-col gap-1 text-sm font-medium">
              <span className="font-mono text-xs">{file}</span>
              <textarea
                aria-label={file}
                value={edits[file] ?? data.files[file]}
                onChange={(e) => setEdits((held) => ({ ...held, [file]: e.target.value }))}
                className={`${areaClass} min-h-48 font-mono text-xs`}
              />
            </label>
          ))}
          <div className="flex gap-2">
            <button type="button" disabled={busy !== null} onClick={() => void saveFiles()} className={quietClass}>
              {t("wizard.step4.saveFiles")}
            </button>
            <button type="button" disabled={busy !== null} onClick={() => void resetFiles()} className={quietClass}>
              {t("wizard.step4.resetFiles")}
            </button>
          </div>
        </details>
      </section>

      <section className={cardClass}>
        <h3 className="text-sm font-semibold">{t("wizard.step4.notStartedTitle")}</h3>
        <p className="mt-1 text-[13px] text-muted-foreground">{t("wizard.step4.notStarted")}</p>
        <h3 className="mt-4 text-sm font-semibold">{t("wizard.step4.nextTitle")}</h3>
        <ol className="mt-1 list-decimal pl-5 text-[13px] text-muted-foreground">
          <li>{t("wizard.step4.next1")}</li>
          <li>{t("wizard.step4.next2")}</li>
          <li>{t("wizard.step4.next3")}</li>
          <li>{t("wizard.step4.next4")}</li>
          <li>{t("wizard.step4.next5")}</li>
        </ol>
      </section>

      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-1" />
        <span>{t("wizard.step4.confirm")}</span>
      </label>

      <ErrorSummary error={error} />
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={!confirmed || busy !== null} className={primaryClass}>
          {busy === "create" ? t("wizard.step4.creating") : t("wizard.step4.create")}
        </button>
        <button type="button" disabled className={`${quietClass} opacity-50`} aria-describedby="start-note">
          {t("wizard.step4.startDisabled")}
        </button>
        <span id="start-note" className="text-[13px] text-muted-foreground">{t("wizard.step4.startNote")}</span>
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Run to verify pass, then typecheck**

Run: `npx vitest run tests/wizardstep4.test.tsx && npm run typecheck`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/wizard/StepReview.tsx web/tests/wizardstep4.test.tsx
git commit -m "web: wizard step 4 — review, Advanced, and create (starts nothing)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 9: The pages, the routes, and the live "+ New project"

`/new` lists the operator's drafts; `/new/:draft/:step` is the wizard. While a save is being reloaded the form is replaced by a pending line, so a quick second submit cannot use a stale revision.

**Files:**
- Create: `web/src/pages/NewProjectsPage.tsx`, `web/src/pages/WizardPage.tsx`
- Modify: `web/src/App.tsx`, `web/src/components/Shell.tsx`, `web/tests/shell.test.tsx`
- Test: `web/tests/wizardpage.test.tsx`

- [ ] **Step 1: Write the failing tests** `web/tests/wizardpage.test.tsx`

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import NewProjectsPage from "@/pages/NewProjectsPage";
import WizardPage from "@/pages/WizardPage";

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

let requested: string[];
let signedIn = true;
let draftBody: Record<string, unknown>;
const baseDraft = {
  draft_id: "d1", revision: 1, status: "open", steps: {}, advanced: {}, figures: {}, project: null,
  last_failure: null, started_at: "t", updated_at: "t",
};

let where = "";
function Where() {
  where = useLocation().pathname;
  return null;
}

function mount(path: string) {
  requested = [];
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    requested.push(`${init?.method ?? "GET"} ${url}`);
    if (url.startsWith("/control/v1/session")) {
      return signedIn ? json(200, { operator: { id: "o1", name: "Ada" }, csrf_token: "t" })
        : json(401, { error: { code: "UNAUTHORIZED", message: "no session" } });
    }
    if (url === "/control/v1/new" && init?.method === "POST") return json(201, { draft_id: "d9", revision: 1 });
    if (url === "/control/v1/new") return json(200, { drafts: [
      { draft_id: "d1", status: "open", revision: 3, steps_saved: [1, 2], project_name: "news-tone", project: null, updated_at: "t" },
      { draft_id: "d2", status: "created", revision: 9, steps_saved: [1, 2, 3], project_name: "done-one", project: "done-one", updated_at: "t" },
    ] });
    if (url === "/control/v1/new/d1") return json(200, draftBody);
    if (url === "/control/v1/new/d1/steps/1") return json(200, { revision: 2, data: {}, figures: { topics: 1, terms: 2 } });
    return json(404, { error: { code: "NOT_FOUND", message: "no" } });
  });
  render(
    <MemoryRouter initialEntries={[path]}>
      <LocaleProvider>
        <SessionProvider>
          <Where />
          <Routes>
            <Route path="/new" element={<NewProjectsPage />} />
            <Route path="/new/:draft/:step" element={<WizardPage />} />
            <Route path="/login" element={<p>login page</p>} />
          </Routes>
        </SessionProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  setCsrfToken(null);
  signedIn = true;
  draftBody = { ...baseDraft };
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("NewProjectsPage", () => {
  it("lists my drafts with their state, and a created one links to its project", async () => {
    mount("/new");
    expect(await screen.findByText("news-tone")).toBeTruthy();
    expect(screen.getByText("2 of 3 steps saved")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the project" }).getAttribute("href")).toBe("/p/done-one");
  });

  it("starting a project creates a draft and opens step 1", async () => {
    mount("/new");
    fireEvent.click(await screen.findByRole("button", { name: "Start a new project" }));
    await waitFor(() => expect(where).toBe("/new/d9/1"));
  });

  it("signed out it offers the sign-in link and shows no draft", async () => {
    signedIn = false;
    mount("/new");
    expect(await screen.findByText(/Sign in to create a project/)).toBeTruthy();
    expect(requested.some((r) => r === "GET /control/v1/new")).toBe(false);
  });
});

describe("WizardPage", () => {
  it("shows step 1 with its explanation, and moves to step 2 after a save", async () => {
    mount("/new/d1/1");
    expect(await screen.findByText("1 · The topic")).toBeTruthy();
    expect(screen.getByText("What Claimstone will do")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Project name/), { target: { value: "news-tone" } });
    fireEvent.change(screen.getByLabelText(/^Topic\b/), { target: { value: "News" } });
    fireEvent.change(screen.getByLabelText(/Search terms/), { target: { value: "a b" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(where).toBe("/new/d1/2"));
    expect(requested).toContain("POST /control/v1/new/d1/steps/1");
  });

  it("a discarded draft says so and shows no form", async () => {
    draftBody = { ...baseDraft, status: "discarded" };
    mount("/new/d1/1");
    expect(await screen.findByText(/This draft was discarded/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save and continue" })).toBeNull();
  });

  it("a created draft shows the created screen, with nothing started", async () => {
    draftBody = { ...baseDraft, status: "created", project: "news-tone" };
    mount("/new/d1/4");
    expect(await screen.findByText("Project created")).toBeTruthy();
    expect(screen.getByText(/Nothing has started/)).toBeTruthy();
  });

  it("an unknown step number falls back to step 1", async () => {
    mount("/new/d1/99");
    expect(await screen.findByText("1 · The topic")).toBeTruthy();
  });

  it("calls no stage, network or model route — only the draft routes", async () => {
    mount("/new/d1/1");
    await screen.findByText("1 · The topic");
    expect(requested.every((r) => r.includes("/control/v1/new") || r.includes("/control/v1/session"))).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/wizardpage.test.tsx`
Expected: FAIL (pages not found).

- [ ] **Step 3: Implement the pages**

`web/src/pages/NewProjectsPage.tsx`:

```tsx
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { DraftSummary } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";

// The operator's own drafts: continue, discard, or start a new one. Drafts are private; the server
// never lists another operator's. Signed out, the page offers the sign-in link and no write control.
export default function NewProjectsPage() {
  const session = useSession();
  const { t } = useLocale();
  if (!session.ready) return <Pending label="…" />;
  if (!session.operator) {
    return (
      <section className="flex flex-col gap-3 pt-6">
        <h1 className="text-[44px] leading-tight">{t("wizard.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("wizard.signIn")}{" "}
          <Link className="underline" to={`/login?next=${encodeURIComponent("/new")}`}>{t("wizard.signInLink")}</Link>
        </p>
      </section>
    );
  }
  return <Drafts />;
}

function nextStep(draft: DraftSummary): number {
  for (const n of [1, 2, 3]) if (!draft.steps_saved.includes(n)) return n;
  return 4;
}

function Drafts() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const list = useApi(() => control.newDrafts(), []);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const made = await control.newStart();
      navigate(`/new/${encodeURIComponent(made.draft_id)}/1`);
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setBusy(false);
    }
  }

  async function discard(draft: DraftSummary) {
    setError(null);
    try {
      await control.newDiscard(draft.draft_id, draft.revision);
      list.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    }
  }

  return (
    <section className="flex flex-col gap-5">
      <header>
        <h1 className="text-[44px] leading-tight">{t("wizard.title")}</h1>
        <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">{t("wizard.lede")}</p>
      </header>
      <div>
        <button
          type="button"
          onClick={() => void start()}
          disabled={busy}
          className="min-h-11 rounded-lg bg-rail px-4 text-sm font-semibold text-rail-foreground disabled:opacity-50"
        >
          {t("wizard.drafts.start")}
        </button>
      </div>
      {error ? <ErrorState error={error} context="drafts" /> : null}
      <section className="rounded-xl bg-card p-5 shadow-sm ring-1 ring-gray-200 dark:ring-gray-800">
        <h2 className="text-base font-semibold">{t("wizard.drafts.title")}</h2>
        {list.error ? (
          <ErrorState error={list.error} context="drafts" />
        ) : list.pending || !list.data ? (
          <Pending label="…" />
        ) : list.data.drafts.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">{t("wizard.drafts.empty")}</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {list.data.drafts.map((draft) => (
              <li key={draft.draft_id} className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-3 text-sm">
                {/* the project name is what the operator typed: shown as typed, never translated */}
                <span className="font-mono">{draft.project_name ?? t("wizard.drafts.untitled")}</span>
                <span className="text-muted-foreground">{t(`wizard.drafts.status.${draft.status}`)}</span>
                <span className="text-muted-foreground">{t("wizard.drafts.stepsSaved", { n: draft.steps_saved.length })}</span>
                <span className="ml-auto flex gap-2">
                  {draft.status === "open" ? (
                    <>
                      <Link className="underline" to={`/new/${encodeURIComponent(draft.draft_id)}/${nextStep(draft)}`}>
                        {t("wizard.drafts.resume")}
                      </Link>
                      <button type="button" className="underline" onClick={() => void discard(draft)}>
                        {t("wizard.drafts.discard")}
                      </button>
                    </>
                  ) : null}
                  {draft.status === "created" && draft.project ? (
                    <Link className="underline" to={`/p/${encodeURIComponent(draft.project)}`}>
                      {t("wizard.drafts.openProject")}
                    </Link>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
```

`web/src/pages/WizardPage.tsx`:

```tsx
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import ErrorState from "@/components/ErrorState";
import Pending from "@/components/Pending";
import ExplainPanel from "@/components/wizard/ExplainPanel";
import StepQuestions from "@/components/wizard/StepQuestions";
import StepReview from "@/components/wizard/StepReview";
import StepSources from "@/components/wizard/StepSources";
import StepTopic from "@/components/wizard/StepTopic";
import WizardShell from "@/components/wizard/WizardShell";
import type { Saved } from "@/components/wizard/stepTypes";
import { useApi } from "@/hooks/useApi";
import { control } from "@/lib/control";
import type { Created, DraftState, Figures } from "@/lib/control";
import { useLocale } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function WizardPage() {
  const { draft: raw = "", step: rawStep = "1" } = useParams();
  const draftId = decodeURIComponent(raw);
  const session = useSession();
  const { t } = useLocale();
  if (!session.ready) return <Pending label="…" />;
  if (!session.operator) {
    const next = `/new/${encodeURIComponent(draftId)}/${encodeURIComponent(rawStep)}`;
    return (
      <section className="flex flex-col gap-3 pt-6">
        <h1 className="text-[44px] leading-tight">{t("wizard.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("wizard.signIn")}{" "}
          <Link className="underline" to={`/login?next=${encodeURIComponent(next)}`}>{t("wizard.signInLink")}</Link>
        </p>
      </section>
    );
  }
  const parsed = Number.parseInt(rawStep, 10);
  const step = (parsed >= 1 && parsed <= 4 ? parsed : 1) as 1 | 2 | 3 | 4;
  return <Wizard draftId={draftId} step={step} />;
}

function Wizard({ draftId, step }: { draftId: string; step: 1 | 2 | 3 | 4 }) {
  const { t } = useLocale();
  const navigate = useNavigate();
  const draftApi = useApi(() => control.newRead(draftId), [draftId]);
  const [justSaved, setJustSaved] = useState<Record<number, Figures>>({});
  const [previewFigures, setPreviewFigures] = useState<Figures>({});
  const [created, setCreated] = useState<Created | null>(null);

  if (draftApi.error) return <ErrorState error={draftApi.error} context="draft" />;
  // While a save is being reloaded the form would hold a stale revision; show a pending line instead.
  if (draftApi.pending || draftApi.refreshing || !draftApi.data) return <Pending label={t("wizard.loading")} />;
  const draft: DraftState = draftApi.data;

  const back = (
    <Link className="underline" to="/new">{t("wizard.backToDrafts")}</Link>
  );
  if (draft.status === "discarded") {
    return <section className="flex flex-col gap-3 pt-6"><p className="text-sm">{t("wizard.discarded")}</p>{back}</section>;
  }
  if (created || draft.status === "created") {
    const name = created?.project ?? draft.project ?? "";
    return (
      <section className="flex flex-col gap-3 pt-6">
        <h1 className="text-[44px] leading-tight">{t("wizard.created.title")}</h1>
        <p className="text-sm">{t("wizard.created.body", { name })}</p>
        {created ? (
          <ul className="font-mono text-xs text-muted-foreground">
            {Object.entries(created.files).map(([file, hash]) => (
              <li key={file}>{file} · {hash}</li>
            ))}
          </ul>
        ) : null}
        <p className="flex gap-4">
          <Link className="underline" to="/projects">{t("wizard.created.projects")}</Link>
          <Link className="underline" to="/new">{t("wizard.created.another")}</Link>
        </p>
      </section>
    );
  }

  const figures: Figures = Object.assign({}, ...Object.values(draft.figures), ...Object.values(justSaved), previewFigures);
  const saved = Object.keys(draft.steps).map(Number);

  const onSaved = (result: Saved) => {
    setJustSaved((held) => ({ ...held, [result.step]: result.figures }));
    draftApi.reload();
    navigate(`/new/${encodeURIComponent(draftId)}/${result.step + 1}`);
  };

  const form =
    step === 1 ? <StepTopic draftId={draftId} draft={draft} onSaved={onSaved} />
    : step === 2 ? <StepQuestions draftId={draftId} draft={draft} onSaved={onSaved} />
    : step === 3 ? <StepSources draftId={draftId} draft={draft} onSaved={onSaved} />
    : (
      <StepReview
        draftId={draftId}
        draft={draft}
        onCreated={(result) => { setCreated(result); draftApi.reload(); }}
        onChanged={() => draftApi.reload()}
        onFigures={setPreviewFigures}
      />
    );

  const projectName = String((draft.steps["1"]?.data as { name?: string } | undefined)?.name ?? "");
  return (
    <section className="flex flex-col gap-5">
      <header>
        <h1 className="text-[44px] leading-tight">{t("wizard.title")}</h1>
        <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">{t("wizard.lede")}</p>
      </header>
      <WizardShell
        draftId={draftId}
        current={step}
        saved={saved}
        explain={<ExplainPanel step={step} figures={figures} extra={{ name: projectName || "—" }} />}
      >
        {form}
      </WizardShell>
    </section>
  );
}
```


- [ ] **Step 4: Wire the routes, the provider and the Shell**

`web/src/App.tsx`: add the imports and routes, and wrap with `LocaleProvider`:

```tsx
import { LocaleProvider } from "@/lib/i18n";
import NewProjectsPage from "@/pages/NewProjectsPage";
import WizardPage from "@/pages/WizardPage";
```

inside the `children` array, after `{ path: "login", … }`:

```tsx
      { path: "new", element: <NewProjectsPage /> },
      { path: "new/:draft/:step", element: <WizardPage /> },
```

and change the `element` of the root route so the provider order is `LocaleProvider` → `SessionProvider` → `Shell`:

```tsx
    element: (
      <LocaleProvider>
        <SessionProvider>
          <Shell />
        </SessionProvider>
      </LocaleProvider>
    ),
```

`web/src/components/Shell.tsx`: replace the disabled button block (the `<div className="flex flex-col min-[900px]:mb-3">` containing the `+ New project` button and its note) with:

```tsx
        <div className="flex flex-col min-[900px]:mb-3">
          <Link
            to={session.operator ? "/new" : `/login?next=${encodeURIComponent("/new")}`}
            className="flex min-h-11 items-center justify-center rounded-lg bg-rail-active px-3 text-sm font-semibold text-rail-foreground"
          >
            {t("shell.newProject")}
          </Link>
        </div>
```

and, in the component body, add `const session = useSession(); const { t } = useLocale();` (import `useSession` from `@/lib/session` — `Shell.tsx` already imports it for the `Operator` component — and `useLocale` from `@/lib/i18n`), plus the language switch in the footer block, next to `<Operator />`:

```tsx
          <LocaleSwitch />
```
with `import LocaleSwitch from "@/components/LocaleSwitch";`.

`web/tests/shell.test.tsx`: replace the test `it("disables New project and says why", …)` with:

```tsx
  it("links New project to the wizard when signed in, and through the login when signed out", async () => {
    mount(true);
    const signedIn = await screen.findByRole("link", { name: "+ New project" });
    expect(signedIn.getAttribute("href")).toBe("/new");
    cleanup();
    mount(false);
    const signedOut = await screen.findByRole("link", { name: "+ New project" });
    expect(signedOut.getAttribute("href")).toBe("/login?next=%2Fnew");
  });
```

- [ ] **Step 5: Run the whole frontend suite**

Run: `npm test && npm run typecheck && npm run build`
Expected: every test passes (including `writes.test.ts`: forms have `onSubmit`; only `control.ts` calls `fetch`), the type check is clean, and `build` passes its CSP check (no inline style). If the CSP check flags an inline style, replace it with a Tailwind class.

- [ ] **Step 6: Commit**

```bash
git add web/src/pages web/src/App.tsx web/src/components/Shell.tsx web/tests
git commit -m "web: the wizard pages, routes, and the live + New project link

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

### Task 10: The i18n scan, the live check and the guide

**Files:**
- Modify: `web/tests/i18n.test.tsx` (add the source scan)
- Create: `tools/check_new_project_wizard.py`
- Modify: `docs/GUIDE.md`, `docs/GUIDE.it.md`

- [ ] **Step 1: Add the "user text never passes through `t()`" scan** (append to `web/tests/i18n.test.tsx`)

```tsx
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

describe("t() is only ever called with a literal key", () => {
  // A variable first argument could carry what a person typed. Literal keys (including template
  // literals with a fixed prefix) cannot.
  const roots = [join(__dirname, "..", "src", "components", "wizard"), join(__dirname, "..", "src", "pages")];
  const files = roots.flatMap((root) =>
    readdirSync(root).filter((f) => /\.tsx?$/.test(f)).map((f) => join(root, f)));

  it("scans the wizard sources", () => {
    expect(files.length).toBeGreaterThan(5);
  });

  it("never passes an identifier as the key", () => {
    const offenders = files.filter((file) =>
      /\bt\(\s*[A-Za-z_]/.test(readFileSync(file, "utf-8")));
    expect(offenders).toEqual([]);
  });
});
```

Run: `npx vitest run tests/i18n.test.tsx`
Expected: pass (all `t(` calls start with a quote or backtick).

- [ ] **Step 2: Write the live check** `tools/check_new_project_wizard.py`

```python
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
            status, made = call(base, cookie, csrf, "POST", f"/new/{draft}/create", {"confirm": True})
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
```

Run: `.venv/bin/python tools/check_new_project_wizard.py`
Expected: prints three "step N saved" lines and ends with `OK: the project loads …`.

- [ ] **Step 3: Add the guide section** — in `docs/GUIDE.md`, insert before `## 1 · discover` this section (and the Italian one in `docs/GUIDE.it.md` before `## 1 · discover — candidati…`):

English:

```markdown
## Creating a project from the portal

Instead of writing the three files by hand, an operator can build a project in the portal: sign in, choose
**+ New project**, and follow four steps. The wizard keeps a **draft** after every step and explains, in
Italian or English, what Claimstone will do with what you entered. Nothing exists under `projects/` until
you confirm the last step, and confirming starts no search, no copy request and no model call.

1. **Topic** — a name, a description and the topics with their search terms.
2. **Questions** — each with a kind; `operational` questions are tracked but never receive a verdict.
3. **Sources and rigour** — the source classes that may count, the acquisition floor with its reason, whether
   supplied copies count toward it, and the field's notation.
4. **Review and create** — the exact files, an Advanced editor for the generated text, and the confirmation.
   Creating writes `topics.yaml`, `questions.yaml` and `sources.yaml`, freezes the question registry and the
   floor at version 1 with today's date, and records each file's hash.

Authorizing and starting the research is a separate stage, not yet in the portal. To check the wizard end to end
without touching a real project: `.venv/bin/python tools/check_new_project_wizard.py`. The routes are described in
[`contracts/new_project.md`](contracts/new_project.md).
```

Italian:

```markdown
## Creare un progetto dal portale

Invece di scrivere a mano i tre file, un operatore può costruire un progetto nel portale: accedi, scegli
**+ Nuovo progetto** e segui quattro passi. Il wizard conserva una **bozza** dopo ogni passo e spiega, in
italiano o in inglese, cosa farà Claimstone con quello che hai inserito. Nulla esiste sotto `projects/` finché
non confermi l'ultimo passo, e confermare non avvia nessuna ricerca, nessuna richiesta di copie e nessuna
chiamata a un modello.

1. **Argomento** — un nome, una descrizione e gli argomenti con i loro termini di ricerca.
2. **Domande** — ciascuna con un tipo; le domande `operational` restano nel progetto ma non ricevono mai un verdetto.
3. **Fonti e rigore** — le classi di fonte che possono contare, la soglia di acquisizione con il suo motivo, se le
   copie fornite da te contano per la soglia, e la notazione del campo.
4. **Riepilogo e creazione** — i file esatti, un editor Avanzate per il testo generato, e la conferma. Creare scrive
   `topics.yaml`, `questions.yaml` e `sources.yaml`, congela il registro delle domande e la soglia alla versione 1
   con la data di oggi e registra l'impronta di ciascun file.

Autorizzare e avviare la ricerca è una tappa separata, non ancora nel portale. Per verificare il wizard da un capo
all'altro senza toccare un progetto reale: `.venv/bin/python tools/check_new_project_wizard.py`. Le rotte sono
descritte in [`contracts/new_project.md`](contracts/new_project.md).
```

- [ ] **Step 4: Full verification**

Run from the repository root:

```bash
.venv/bin/pytest -q
.venv/bin/claimstone validate --all-projects
.venv/bin/python tools/check_new_project_wizard.py
cd web && npm test && npm run typecheck && npm run build
```

Expected: all green; the live check ends with `OK`.

- [ ] **Step 5: Manual check in a browser** (once, before announcing)

```bash
.venv/bin/claimstone operator add me --name "Me"                        # once
.venv/bin/claimstone control --allow-host localhost:5173 &
.venv/bin/claimstone api &
cd web && npm run dev                                                   # http://localhost:5173/new
```

Walk the four steps in English and in Italian, at a wide window and below 900 px; confirm the explanation panel
turns into an accordion, a refused step shows its message under the field, the Start button stays disabled, and the
created project then appears under `/projects`. Remove the throwaway directory afterwards: `rm -r projects/<name>`
(it is gitignored).

- [ ] **Step 6: Commit**

```bash
git add web/tests/i18n.test.tsx tools/check_new_project_wizard.py docs/GUIDE.md docs/GUIDE.it.md
git commit -m "wizard: i18n key scan, the live check, and the guide section

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XK9eTSwsZuStkHXC6YAaAE"
```

---

## Self-review (spec coverage)

| Spec requirement | Task |
|---|---|
| Four steps, each saves a draft; Start disabled with its explanation | 6, 7, 8 |
| Explanation of every phase, IT + EN, three moments per step, figures from the server | 3, 5 |
| Unknown is "—", never 0 | 4, 5 |
| Layout: panel right on desktop, accordion under 900 px | 5 |
| Guided essentials; nothing defaulted silently (classes, supplied copies) | 7 |
| Advanced editor with server validation (browser never parses YAML) | 8 |
| i18n infrastructure per the 2026-10-07 design; user text never through `t()` | 2, 10 |
| Field-path errors, stale revision, keep typed text | 1, 4, 6 |
| `+ New project` live for signed-in operators; sign-in path otherwise | 9 |
| Only `control.ts` writes; forms have `onSubmit`; no inline style (CSP) | 9 (suite) |
| Live check and guide | 10 |

**Type consistency:** `Saved`, `StepProps` (Task 6) are used by Tasks 7 and 9; `Created`, `DraftState`, `Preview`, `Figures` (Task 1) by Tasks 8–9; `explainParams` keys (Task 4) match the catalog placeholders (Task 3): `topics terms searches searchesAll total literature operational floor classes added supplied name hosts`. `hosts` is passed directly in `StepSources` and `name` through `extra`.
