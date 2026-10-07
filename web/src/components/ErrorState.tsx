import { ApiError } from "@/lib/api";
import { ControlError } from "@/lib/control";

// §4.2 rule 1 and §3.3: every error code renders as a named state with its message —
// never an empty table. LEDGER_CORRUPT names the ledger and line it damaged.
export default function ErrorState({
  error,
  context = "",
}: {
  error: ApiError | ControlError | Error;
  context?: string;
}) {
  // v2.1 rule 3: an ApiError or ControlError shows the server's own code and message.
  const code =
    error instanceof ApiError || error instanceof ControlError ? error.code : "UNREACHABLE";
  return (
    <div className="error" role="alert">
      <span className="code" data-error-code={code}>
        {code}
      </span>
      {context ? <span className="context">{context}</span> : null}
      <p className="message">{error.message}</p>
    </div>
  );
}
