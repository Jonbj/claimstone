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
