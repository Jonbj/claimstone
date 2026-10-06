import { useState } from "react";

// §4.2 rule 4: no verdict input of any kind. This shows a CLI command with its
// placeholders and a copy button; it never executes anything.
export default function CommandBlock({ command, note = "" }: { command: string; note?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard permission denied: the text stays selectable, nothing executes
      setCopied(false);
    }
  }

  return (
    <div className="command-block">
      {note ? <p className="note">{note}</p> : null}
      <div className="row">
        <code>{command}</code>
        <button type="button" onClick={copy} aria-label="copy command to clipboard">
          {copied ? "copied" : "copy"}
        </button>
      </div>
    </div>
  );
}
