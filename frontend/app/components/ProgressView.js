'use client'

const STAGES = [
  ['transcribing', 'Transcribing the recording'],
  ['cleaning', 'Cleaning the transcript and splitting it by topic'],
  ['enriching', 'Finding gaps and searching the web'],
  ['writing', 'Writing the notes'],
  ['judging', 'Checking every statement against its source'],
  ['exporting', 'Writing slides and files'],
]

export default function ProgressView({ job }) {
  const current = STAGES.findIndex(([key]) => key === job.stage)
  const failed = job.status === 'error'
  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold">{failed ? 'Something went wrong' : 'Working on your lecture…'}</h2>
      <ol className="flex flex-col gap-2">
        {STAGES.map(([key, label], index) => {
          const isDone = !failed && (job.status === 'done' || index < current)
          const isCurrent = index === current
          const isFailed = failed && isCurrent
          return (
            <li key={key} className="flex items-center gap-3">
              <span
                aria-hidden
                className={`flex h-6 w-6 items-center justify-center rounded-full text-xs text-white ${
                  isFailed ? 'bg-red-600' : isDone ? 'bg-green-600' : isCurrent ? 'animate-pulse bg-blue-600' : 'bg-zinc-400 dark:bg-zinc-600'
                }`}
              >
                {isFailed ? '!' : isDone ? '✓' : index + 1}
              </span>
              <span className={isCurrent || isDone ? '' : 'text-zinc-500'}>
                {label}
                {isCurrent && !failed && <span className="sr-only"> (in progress)</span>}
              </span>
            </li>
          )
        })}
      </ol>
      {!failed && <p className="text-sm text-zinc-500">A one-hour lecture can take several minutes. You can leave this page open.</p>}
    </div>
  )
}
