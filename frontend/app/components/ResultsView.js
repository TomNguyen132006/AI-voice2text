'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { clock, duration, fileUrl, getStats, zipUrl } from '../lib/api'
import { LOCAL_DIR } from '../lib/localCopy'
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
    kinds[s.id] = !verdict ? 'checked' : verdict === 'unjudged' ? 'unjudged' : 'rewritten'
  }
  return kinds
}

function Figure({ value, label }) {
  return (
    <div className="flex flex-col">
      <dd className="font-serif text-3xl leading-none tabular-nums text-foreground">{value}</dd>
      <dt className="mt-1 text-sm text-muted-foreground">{label}</dt>
    </div>
  )
}

// The per-note status written in the file of a private local copy (each note keeps its own: light notes are never "source-checked").
const KIND_OF_STATUS = { 'source-checked': 'checked', rewritten: 'rewritten', 'not judged': 'unjudged' }

// A private course: the numbers are counted from the notes themselves.
function LocalSummary({ job, sectionCount }) {
  const { statements, summary } = job
  const count = (kind) => statements.filter((s) => KIND_OF_STATUS[s.status] === kind).length
  const rewritten = count('rewritten')
  const checked = count('checked') + rewritten // a rewritten note passed the second check
  const notJudged = statements.length - checked
  return (
    <div className="flex flex-col gap-3">
      <dl className="story-panel grid grid-cols-2 gap-x-4 gap-y-5 !p-5 sm:grid-cols-3">
        <Figure value={summary.lectures} label="lectures" />
        <Figure value={sectionCount} label="sections" />
        <Figure value={statements.length} label="notes" />
        <Figure value={checked} label="source-checked" />
        <Figure value={rewritten} label="of those rewritten" />
        <Figure value={notJudged} label="not judged" />
      </dl>
      <p className="font-semibold">
        Mixed: {checked} source-checked, {notJudged} not judged
      </p>
      <p className="text-muted-foreground">Only some lectures went through the judge. Each note below shows its own status.</p>
      <p className="text-sm text-muted-foreground">
        <strong className="text-foreground">Source-checked</strong> means the cited source supports the note. It does not check that the source itself is true.
      </p>
    </div>
  )
}

function Summary({ job, sectionCount }) {
  const { summary, statements } = job
  if (summary.local) return <LocalSummary job={job} sectionCount={sectionCount} />
  if (summary.sample) {
    return (
      <div className="flex flex-col gap-3">
        <p className="rounded-2xl bg-accent px-4 py-3 text-accent-foreground">
          This is <strong>sample data</strong>, written by hand to show the layout. A model did not write it.
        </p>
        <dl className="story-panel grid grid-cols-2 gap-4 !p-5">
          <Figure value={sectionCount} label="sections" />
          <Figure value={statements.length} label="notes" />
        </dl>
      </div>
    )
  }
  const checked = summary.kept === undefined ? null : summary.kept - (summary.kept_unjudged || 0)
  return (
    <div className="flex flex-col gap-3">
      <dl className="story-panel grid grid-cols-2 gap-x-4 gap-y-5 !p-5 sm:grid-cols-3">
        <Figure value={sectionCount} label="sections" />
        <Figure value={statements.length} label="notes" />
        {checked !== null && <Figure value={checked} label="source-checked" />}
        {typeof summary.fixed === 'number' && <Figure value={summary.fixed} label="rewritten" />}
        {typeof summary.total_seconds === 'number' && <Figure value={duration(summary.total_seconds)} label="processing time" />}
        {typeof summary.est_cost_usd === 'number' && <Figure value={`$${summary.est_cost_usd.toFixed(3)}`} label="model cost" />}
      </dl>
      {summary.dropped > 0 && (
        <p className="text-muted-foreground">{summary.dropped} {summary.dropped === 1 ? 'note was' : 'notes were'} removed because the judge could not confirm {summary.dropped === 1 ? 'it' : 'them'} against {summary.dropped === 1 ? 'its' : 'their'} sources.</p>
      )}
      {summary.kept_unjudged > 0 && <p className="text-muted-foreground">{summary.kept_unjudged} {summary.kept_unjudged === 1 ? 'note was' : 'notes were'} kept without a verdict because the judge failed.</p>}
      {(summary.warnings || []).map((warning) => (
        <p key={warning} className="text-muted-foreground">
          Note: {warning}
        </p>
      ))}
      <p className="text-sm text-muted-foreground">
        <strong className="text-foreground">Source-checked</strong> means the cited source supports the note. It does not check that the source itself is true.
      </p>
    </div>
  )
}

function DownloadIcon() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 2.5v8m0 0L5 7.5m3 3l3-3M3 13h10" />
    </svg>
  )
}

function DownloadButton({ label, path, example, filename }) {
  if (!path) {
    return (
      <span aria-disabled="true" className="story-button story-button-outline story-button-small w-full sm:w-auto">
        {label} (not available)
      </span>
    )
  }
  return (
    <a
      href={example ? path : fileUrl(path)}
      download={example ? `lecturesque-${filename}` : undefined}
      className="story-button story-button-outline story-button-small w-full sm:w-auto"
    >
      <DownloadIcon />
      {label}
    </a>
  )
}

// The original audio of a pre-generated example. preload="none": nothing is downloaded until someone plays it.
function LecturePlayer({ audioRef, src, credit }) {
  return (
    <div className="story-panel flex flex-col gap-3 !p-5">
      <p className="story-label text-muted-foreground">Original lecture audio (excerpt)</p>
      <audio ref={audioRef} controls preload="none" src={src} className="block w-full max-w-full" />
      <p className="text-sm text-muted-foreground">{credit}</p>
    </div>
  )
}

// example: a pre-generated example (frontend/public/examples), opened without the backend: static files, no stats request.
// local: a private copy on this computer { deck, notes } (file names in /local-only/): static files, no stats request, own downloads.
export default function ResultsView({ job, onReset, example, local }) {
  const [stats, setStats] = useState(example || local ? null : undefined) // undefined: loading, null: none
  useEffect(() => {
    if (example || local) return
    let cancelled = false
    getStats(job.id)
      .then((value) => !cancelled && setStats(value))
      .catch(() => !cancelled && setStats(null))
    return () => {
      cancelled = true
    }
  }, [job.id, example, local])

  // A lecture chip on an example plays the audio from its time. The file may not be loaded yet (preload="none"): load it first.
  const audio = useRef(null)
  const seek = useCallback((seconds) => {
    const el = audio.current
    if (!el) return
    const go = () => {
      el.currentTime = seconds
      el.play().catch(() => {})
    }
    if (el.readyState >= 1) go()
    else {
      el.addEventListener('loadedmetadata', go, { once: true })
      el.load()
    }
  }, [])

  const kinds = useMemo(
    () => (local ? Object.fromEntries(job.statements.map((s) => [s.id, KIND_OF_STATUS[s.status] || 'unjudged'])) : judgeKinds(stats, job.statements)),
    [local, stats, job.statements],
  )
  const groups = (job.sections.length ? job.sections : [{ id: 'all', title: 'Notes', start: 0, end: 0 }])
    .map((section) => ({ section, notes: job.sections.length ? job.statements.filter((s) => s.section_id === section.id) : job.statements }))
    .filter((group) => group.notes.length > 0)

  return (
    <div className="flex flex-col gap-10">
      <section aria-labelledby="result-heading" className="flex flex-col gap-6">
        <div>
          <p className="handwritten">all done ✦</p>
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h2 id="result-heading" className="text-4xl leading-tight">
              Your study notes
            </h2>
            <button type="button" onClick={onReset} className="story-link cursor-pointer">
              New lecture
            </button>
          </div>
        </div>
        {example && (
          <div role="note" className="flex flex-col gap-1 rounded-2xl bg-accent px-4 py-3 text-accent-foreground">
            <p className="font-semibold">This is a pre-generated example, not a live run.</p>
          </div>
        )}
        {local && (
          <div role="note" className="flex flex-col gap-1 rounded-2xl bg-accent px-4 py-3 text-accent-foreground">
            <p className="font-semibold">Private local copy. Only on this computer. Not uploaded, not part of the site.</p>
          </div>
        )}
        {example && <LecturePlayer audioRef={audio} src={`${example.files}/lecture.mp3`} credit={example.credit} />}
        <Summary job={job} sectionCount={groups.length} />
        <div>
          <h3 className="sr-only">Downloads</h3>
          {local ? (
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              <a href={`${LOCAL_DIR}${local.deck}`} download className="story-button story-button-coral w-full sm:w-auto">
                <DownloadIcon />
                Slides (.pptx)
              </a>
              <a href={`${LOCAL_DIR}${local.notes}`} download className="story-button story-button-outline w-full sm:w-auto">
                <DownloadIcon />
                Notes (.md)
              </a>
            </div>
          ) : (
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              <a
                href={example ? `${example.files}/all.zip` : zipUrl(job.id)}
                download={example ? 'lecturesque-all.zip' : undefined}
                className="story-button story-button-coral w-full sm:w-auto"
              >
                <DownloadIcon />
                All files (.zip)
              </a>
              <DownloadButton label="Notes (.md)" path={job.outputs.md} example={Boolean(example)} filename="notes.md" />
              <DownloadButton label="Slides (.pptx)" path={job.outputs.pptx} example={Boolean(example)} filename="slides.pptx" />
              <DownloadButton label="Transcript (.txt)" path={job.outputs.txt} example={Boolean(example)} filename="transcript.txt" />
            </div>
          )}
        </div>
      </section>

      {groups.length === 0 && (
        <p className="story-panel">No note passed the checks, so there is nothing to show. Try a different transcript.</p>
      )}

      {groups.map(({ section, notes }, index) => (
        <section key={section.id} aria-labelledby={`h-${section.id}`} className="flex flex-col gap-5 border-t border-border pt-8">
          <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
            <div className="min-w-0 flex-1">
              <p className="story-label text-muted-foreground">SECTION {index + 1}</p>
              <h3 id={`h-${section.id}`} className="mt-1 text-3xl leading-tight">
                {section.title}
              </h3>
            </div>
            {section.end > 0 && (
              <p className="story-label inline-flex shrink-0 items-center rounded-full bg-accent px-3.5 py-1.5 text-accent-foreground tabular-nums">
                {clock(section.start)} – {clock(section.end)}
              </p>
            )}
          </header>
          <ul className="flex flex-col gap-7">
            {notes.map((note) => (
              <li key={note.id} className="flex flex-col gap-2.5">
                <p className="text-[18px] leading-[1.7] text-foreground">{note.text}</p>
                <div className="flex flex-wrap items-center gap-2">
                  {note.sources.map((source, i) =>
                    source.type === 'web' ? <WebChip key={`${note.id}-${i}`} source={source} /> : <LectureChip key={`${note.id}-${i}`} source={source} onSeek={example ? seek : undefined} />,
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
