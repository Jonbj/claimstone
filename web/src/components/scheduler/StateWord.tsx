import Chip from "@/components/Chip";
import { useLocale } from "@/lib/i18n";
import { stateLabelKey } from "./labels";

// A server state word: the translated label as the visible text, the raw word in the title. A word
// the table does not know is shown as sent.
export default function StateWord({ word }: { word: string }) {
  const { t } = useLocale();
  const key = stateLabelKey(word);
  return <Chip text={word} title={word} label={key ? t(key) : word} />;
}
