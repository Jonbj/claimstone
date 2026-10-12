import { useLocale } from "@/lib/i18n";

/** "1 round" / "2 rounds": the plural is chosen here, from two catalog keys. */
export default function Rounds({ n }: { n: number }) {
  const { t } = useLocale();
  return <>{t(n === 1 ? "sched.index.rounds.one" : "sched.index.rounds.other", { n })}</>;
}
