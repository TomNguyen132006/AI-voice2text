// A human error message with a way out. Never shows JSON or a stack trace: callers pass words from describeError().
export default function ErrorNotice({ title, message, detail, onRetry, retryLabel = 'Try again', onSecondary, secondaryLabel }) {
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-lg border border-danger/40 bg-danger-soft px-4 py-4">
      <div>
        <p className="font-semibold text-danger">{title}</p>
        <p className="mt-1 text-ink">{message}</p>
      </div>
      {detail && (
        <details className="text-muted">
          <summary className="cursor-pointer">Details from the server</summary>
          <p className="mt-1 break-words">{detail}</p>
        </details>
      )}
      <div className="flex flex-col gap-2 sm:flex-row">
        {onRetry && (
          <button type="button" onClick={onRetry} className="rounded-lg bg-danger px-5 py-2.5 font-medium text-white hover:opacity-90">
            {retryLabel}
          </button>
        )}
        {onSecondary && (
          <button type="button" onClick={onSecondary} className="rounded-lg border border-danger px-5 py-2.5 font-medium text-danger hover:bg-white/60">
            {secondaryLabel}
          </button>
        )}
      </div>
    </div>
  )
}
