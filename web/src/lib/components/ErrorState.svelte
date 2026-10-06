<script lang="ts">
  // §4.2 rule 1 and §3.3: every error code renders as a named state with its message —
  // never an empty table. LEDGER_CORRUPT names the ledger and line it damaged.
  import { ApiError } from "$lib/api";
  let { error, context = "" }: { error: ApiError | Error; context?: string } = $props();

  const code = $derived(error instanceof ApiError ? error.code : "UNREACHABLE");
</script>

<div class="error" role="alert">
  <span class="code" data-error-code={code}>{code}</span>
  {#if context}<span class="context">{context}</span>{/if}
  <p class="message">{error.message}</p>
</div>

<style>
  .error {
    border: 1px solid var(--error);
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
    margin: 0.5rem 0;
  }
  .code {
    font-weight: 600;
    color: var(--error);
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 0.8rem;
  }
  .context {
    color: var(--muted);
    margin-left: 0.5rem;
    font-size: 0.8rem;
  }
  .message {
    margin: 0.25rem 0 0;
    white-space: pre-wrap;
  }
</style>