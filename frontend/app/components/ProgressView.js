'use client'

import { STAGES, duration } from '../lib/api'
import { useNow } from '../lib/hooks'

function Marker({ state }) {
  const base = 'flex h-7 w-7 items-center justify-center rounded-full'
  if (state === 'running') {
    return (
      <span aria-hidden className={`${base} bg-surface`}>
        <span className="inline-block h-6 w-6 animate-spin rounded-full border-[3px] border-accent-soft border-t-accent" />
      </span>
    )
  }
  if (state === 'done') {
    return (
      <span aria-hidden className={`${base} bg-accent text-white`}>
        <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 8.5l3.2 3L13 4.5" />
        </svg>
      </span>
    )
  }
  if (state === 'failed') {
    return (
      <span aria-hidden className={`${base} bg-danger text-white`}>
        <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
        </svg>
      </span>
    )
  }
  return <span aria-hidden className={`${base} border-2 border-line-strong bg-surface`} />
}

const WORDS = { waiting: 'Waiting', running: 'Running', done: 'Done', failed: 'Failed' }

export default function ProgressView({ job, log, waking }) {
  const failed = job.status === 'error'
  const current = STAGES.findIndex(([key]) => key === job.stage)
  const live = !failed && job.status !== 'done'
  const now = useNow(live)

  const starts = Object.values(log).map((entry) => entry.start)
  const first = starts.length ? Math.min(...starts) : 0
  const total = live && first && now ? (now - first) / 1000 : null

  return (
    <section aria-labelledby="running-heading" className="flex flex-col gap-5">
      <div>
        <h2 id="running-heading" className="text-2xl font-bold">
          {failed ? 'This lecture could not be finished' : 'Working on your lecture'}
        </h2>
        <p className="mt-1 min-h-6 text-muted">
          {live
            ? `${job.status === 'queued' ? 'Waiting for the server to start the job. ' : ''}${total !== null ? `${duration(total)} so far. ` : ''}You can leave this page open.`
            : ''}
        </p>
      </div>
      {waking && live && (
        <p role="status" className="rounded-lg border border-accent/30 bg-accent-soft px-4 py-3 text-accent-ink">
          The server is waking up or slow to answer. On the free plan the first request can take about 30 seconds. Keep this page open.
        </p>
      )}
      <p role="status" aria-live="polite" className="sr-only">
        {live && current >= 0 ? `Now: ${STAGES[current][1]}` : failed ? 'The job failed' : ''}
      </p>
      <ol className="rounded-xl border border-line bg-surface px-4 py-5 sm:px-6">
        {STAGES.map(([key, title, what], index) => {
          const state = failed && index === current ? 'failed' : index < current || job.status === 'done' ? 'done' : index === current ? 'running' : 'waiting'
          const entry = log[key]
          const seconds = entry?.start ? ((entry.end || (state === 'running' ? now : 0)) - entry.start) / 1000 : null
          const last = index === STAGES.length - 1
          return (
            <li
              key={key}
              aria-current={state === 'running' ? 'step' : undefined}
              className={`relative flex items-start gap-4 ${last ? '' : 'pb-6 after:absolute after:top-9 after:bottom-0 after:left-[13px] after:w-0.5 after:bg-line'}`}
            >
              <span className="relative z-10 mt-0.5">
                <Marker state={state} />
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className={`font-semibold ${state === 'waiting' ? 'text-muted' : 'text-navy'}`}>{title}</span>
                <span className="text-muted">{what}</span>
              </span>
              <span className="flex min-w-16 flex-col items-end text-right">
                <span className={`font-semibold ${state === 'failed' ? 'text-danger' : state === 'waiting' ? 'text-muted' : 'text-accent-ink'}`}>{WORDS[state]}</span>
                <span className="min-h-6 text-muted tabular-nums">{seconds !== null && seconds >= 0 && (state !== 'running' || now) ? duration(seconds) : ''}</span>
              </span>
            </li>
          )
        })}
      </ol>
      <p className="text-sm text-muted">Times are measured in this browser. The server reports six steps, so some rows cover two jobs.</p>
    </section>
  )
}
