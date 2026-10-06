import { word } from "@/lib/vocabulary";
import { cn } from "@/lib/utils";

// §4.2 rule 7: colour never carries meaning alone — the word is always there.
// The class names come from vocabulary.ts, which never invents words.
export default function Chip({ text, title = "" }: { text: string; title?: string }) {
  const w = word(text);
  return (
    <span className={cn("chip", w.cls, w.dashed && "dashed")} title={title || text}>
      {text}
    </span>
  );
}
