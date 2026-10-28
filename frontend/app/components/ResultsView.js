'use client'

import { useEffect, useMemo, useState } from 'react'
import { clock, duration, fileUrl, getStats, zipUrl } from '../lib/api'
import { JudgeBadge, LectureChip, WebChip } from './Chips'
import StatsPanel from './StatsPanel'

// What the judge decided for each kept note, worked out from the stats of the same job:
// a note that failed the first check and is still here was rewritten and passed the second check.
// Only when the stats list every rejection (they cut the list at 20); otherwise no badges.
function judgeKinds(stats, statements) {
  if (!stats?.available || !stats.judge || stats.judge.more_rejections > 0) return {}
  const rejected = Object.fromEntries((stats.judge.rejections || []).map((r) => [r.statement_id, r.verdict]))
  const kinds = {}
  for (const s of statements) {
    const verdict = rejected[s.id]
    kinds[s.id] = !verdict ? 'verified' : verdict === 'unjudged' ? 'unjudged' : 'rewritten'
  }
  return kinds
}

function Figure({ value, label }) {
  return (
    <div className="flex flex-col">
      <dd className="font-read text-2xl font-semibold tabular-nums">{value}</dd>
      <dt className="text-muted">{label}</dt>
    </div>
  )
}

function Summary({ job, sectionCount }) {
  const { summary, statements } = job
  if (summary.sample) {
    return (
      <div className="flex flex-col gap-3">
        <p className="rounded-lg border border-accent/30 bg-accent-soft px-4 py-3 text-accent-ink">
          This is <strong>sample data</strong>, written by hand to show the layout. A model did not write it.
        </p>
        <dl className="grid grid-cols-2 gap-4">
          <Figure value={sectionCount} label="sections" />
          <Figure value={statements.length} label="notes" />
        </dl>
      </div>
    )
  }
  const verified = summary.kept === undefined ? null : summary.kept - (summary.kept_unjudged || 0)
  return (
    <div className="flex flex-col gap-3">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-3 lg:grid-cols-6">
        <Figure value={sectionCount} label="sections" />
        <Figure value={statements.length} label="notes" />
        {verified !== null && <Figure value={verified} label="verified by the judge" />}
        {typeof summary.fixed === 'number' && <Figure value={summary.fixed} label="rewritten" />}
        {typeof summary.total_seconds === 'number' && <Figure value={duration(summary.total_seconds)} label="processing time" />}
        {typeof summary.est_cost_usd === 'number' && <Figure value={`$${summary.est_cost_usd.toFixed(3)}`} label="model cost" />}
      </dl>
      {summary.dropped > 0 && (
        <p className="text-muted">{summary.dropped} notes were removed because the judge could not confirm them against their sources.</p>
      )}
      {summary.kept_unjudged > 0 && <p className="text-muted">{summary.kept_unjudged} notes were kept without a verdict because the judge failed.</p>}
      {(summary.warnings || []).map((warning) => (
        <p key={warning} className="text-muted">
          Note: {warning}
        </p>
      ))}
    </div>
  )
}

function DownloadButton({ label, path, primary }) {
  const base = 'inline-flex w-full items-center justify-center rounded-lg px-5 py-2.5 font-medium sm:w-auto'
  if (!path) {
    return (
      <span aria-disabled="true" className={`${base} border border-line text-muted`}>
        {label} (not available)
      </span>
    )
  }
  return (
    <a
      href={fileUrl(path)}
      className={`${base} ${primary ? 'bg-accent text-white hover:bg-accent-ink' : 'border border-accent text-accent hover:bg-accent-soft'}`}
    >
      {label}
    </a>
  )
}

export default function ResultsView({ job, onReset }) {
  const [stats, setStats] = useState(undefined) // undefined: loading, null: none
  useEffect(() => {
    let cancelled = false
    getStats(job.id)
      .then((value) => !cancelled && setStats(value))
      .catch(() => !cancelled && setStats(null))
    return () => {
      cancelled = true
    }
  }, [job.id])

  const kinds = useMemo(() => judgeKinds(stats, job.statements), [stats, job.statements])
  const groups = (job.sections.length ? job.sections : [{ id: 'all', title: 'Notes', start: 0, end: 0 }])
    .map((section) => ({ section, notes: job.sections.length ? job.statements.filter((s) => s.section_id === section.id) : job.statements }))
    .filter((group) => group.notes.length > 0)

  return (
    <div className="flex flex-col gap-10">
      <section aria-labelledby="result-heading" className="flex flex-col gap-6">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="result-heading" className="font-read text-3xl font-semibold">
            Your study notes
          </h2>
          <button type="button" onClick={onReset} className="font-medium text-accent underline underline-offset-2">
            New lecture
          </button>
        </div>
        <Summary job={job} sectionCount={groups.length} />
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <a
            href={zipUrl(job.id)}
            className="inline-flex w-full items-center justify-center rounded-lg bg-accent px-5 py-2.5 font-medium text-white hover:bg-accent-ink sm:w-auto"
          >
            All files (.zip)
          </a>
          <DownloadButton label="Notes (.md)" path={job.outputs.md} />
          <DownloadButton label="Slides (.pptx)" path={job.outputs.pptx} />
          <DownloadButton label="Transcript (.txt)" path={job.outputs.txt} />
        </div>
      </section>

      {groups.length === 0 && (
        <p className="rounded-lg border border-line bg-surface px-4 py-4">
          No note passed the checks, so there is nothing to show. Try a different transcript.
        </p>
      )}

      {groups.map(({ section, notes }) => (
        <section key={section.id} aria-labelledby={`h-${section.id}`} className="flex flex-col gap-5 border-t border-line pt-8">
          <header>
            <h3 id={`h-${section.id}`} className="font-read text-2xl font-semibold">
              {section.title}
            </h3>
            {section.end > 0 && (
              <p className="text-muted">
                Lecture time {clock(section.start)} – {clock(section.end)}
              </p>
            )}
          </header>
          <ul className="flex flex-col gap-7">
            {notes.map((note) => (
              <li key={note.id} className="flex flex-col gap-2">
                <p className="font-read text-lg leading-relaxed">{note.text}</p>
                <div className="flex flex-wrap items-center gap-2">
                  {note.sources.map((source, i) =>
                    source.type === 'web' ? <WebChip key={`${note.id}-${i}`} source={source} /> : <LectureChip key={`${note.id}-${i}`} source={source} />,
                  )}
                  {kinds[note.id] && <JudgeBadge kind={kinds[note.id]} />}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}

      <StatsPanel stats={stats} statements={job.statements} />
    </div>
  )
}
