// A human error message with a way out. Never shows JSON or a stack trace: callers pass words from describeError().
export default function ErrorNotice({ title, message, detail, onRetry, retryLabel = 'Try again', onSecondary, secondaryLabel }) {
  return (
    <div role="alert" className="flex gap-3 rounded-xl border border-danger/40 border-l-4 border-l-danger bg-danger-soft px-4 py-4 sm:px-5">
      <svg aria-hidden viewBox="0 0 20 20" width="22" height="22" className="mt-0.5 shrink-0 text-danger" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="10" cy="10" r="8" />
        <path d="M10 6v5M10 14h.01" />
      </svg>
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div>
          <p className="text-lg font-bold text-danger">{title}</p>
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
            <button type="button" onClick={onRetry} className="btn border border-danger bg-danger text-white hover:opacity-90">
              {retryLabel}
            </button>
          )}
          {onSecondary && (
            <button type="button" onClick={onSecondary} className="btn border border-danger bg-surface text-danger hover:bg-white/60">
              {secondaryLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
