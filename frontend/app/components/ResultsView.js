'use client'

import { useState } from 'react'
import { clock, fileUrl, zipUrl } from '../lib/api'
import StatsPanel from './StatsPanel'

function LectureCitation({ source }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="inline-flex items-center gap-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="rounded bg-amber-500/15 px-1.5 py-0.5 text-xs font-medium text-amber-700 hover:bg-amber-500/30 dark:text-amber-300"
      >
        📍 {clock(source.start)}
      </button>
      {open && (
        <span className="text-xs text-zinc-500">
          Lecture {clock(source.start)} – {clock(source.end)} ({source.segment_id})
        </span>
      )}
    </span>
  )
}

function WebCitation({ source }) {
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded bg-blue-500/15 px-1.5 py-0.5 text-xs font-medium text-blue-700 hover:bg-blue-500/30 dark:text-blue-300"
    >
      🌐 {source.title || source.url}
    </a>
  )
}

function Summary({ summary, count }) {
  if (summary.sample) {
    return (
      <p className="rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-sm">
        This is <strong>sample data</strong> written by hand to show the layout. It is not the output of a model.
      </p>
    )
  }
  if (summary.kept === undefined) return null
  const parts = [
    `${summary.kept} statements kept`,
    `${summary.passed_first_time ?? 0} passed the check the first time`,
    summary.fixed ? `${summary.fixed} rewritten after a failed check` : null,
    summary.dropped ? `${summary.dropped} removed` : null,
    summary.kept_unjudged ? `${summary.kept_unjudged} not checked (the judge failed)` : null,
  ].filter(Boolean)
  return (
    <div className="rounded-lg border border-zinc-300 p-3 text-sm dark:border-zinc-700">
      <p>
        <strong>Checked by the judge:</strong> {parts.join(' · ')}.
      </p>
      {(summary.total_seconds || summary.model_calls) && (
        <p className="text-zinc-500">
          {summary.total_seconds ? `${Math.round(summary.total_seconds)} s` : ''}
          {summary.model_calls ? ` · ${summary.model_calls} model calls` : ''}
          {typeof summary.est_cost_usd === 'number' ? ` · about $${summary.est_cost_usd.toFixed(3)}` : ''}
        </p>
      )}
      {(summary.warnings || []).map((w) => (
        <p key={w} className="text-amber-700 dark:text-amber-300">
          Note: {w}
        </p>
      ))}
      {count === 0 && <p className="mt-1 text-red-600">No statement passed the checks, so there are no notes.</p>}
    </div>
  )
}

export default function ResultsView({ job, onReset }) {
  const sections = job.sections.length ? job.sections : [{ id: 'all', title: 'Notes', start: 0, end: 0 }]
  const downloads = [
    ['Notes (.md)', job.outputs.md],
    ['Slides (.pptx)', job.outputs.pptx],
    ['Transcript (.txt)', job.outputs.txt],
  ]
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-semibold">Your study notes</h2>
        <button type="button" onClick={onReset} className="text-sm underline">
          Start over
        </button>
      </div>
      <Summary summary={job.summary || {}} count={job.statements.length} />
      <StatsPanel jobId={job.id} />
      <div className="flex flex-wrap gap-2">
        <a href={zipUrl(job.id)} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
          Download all (.zip)
        </a>
        {downloads.map(([label, path]) =>
          path ? (
            <a
              key={label}
              href={fileUrl(path)}
              className="rounded-lg border border-zinc-400 px-4 py-2 text-sm font-medium hover:bg-zinc-500/10 dark:border-zinc-600"
            >
              {label}
            </a>
          ) : null,
        )}
      </div>
      {sections.map((section) => {
        const own = job.sections.length ? job.statements.filter((s) => s.section_id === section.id) : job.statements
        if (own.length === 0) return null
        return (
          <section key={section.id} className="flex flex-col gap-3">
            <h3 className="text-lg font-semibold">
              {section.title}
              {section.end > 0 && (
                <span className="ml-2 text-sm font-normal text-zinc-500">
                  {clock(section.start)} – {clock(section.end)}
                </span>
              )}
            </h3>
            <ul className="flex flex-col gap-3">
              {own.map((statement) => (
                <li key={statement.id} className="rounded-lg border border-zinc-300 p-3 dark:border-zinc-700">
                  <p>{statement.text}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {statement.sources.map((source, i) =>
                      source.type === 'web' ? (
                        <WebCitation key={`${statement.id}-${i}`} source={source} />
                      ) : (
                        <LectureCitation key={`${statement.id}-${i}`} source={source} />
                      ),
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
