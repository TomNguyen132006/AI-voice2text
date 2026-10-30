'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { getJob } from '../lib/api'
import { EXAMPLES } from '../lib/examples'
import { isLocalHost, LOCAL_DIR } from '../lib/localCopy'
import { clearRecent, updateRecent, useRecentJobs } from '../lib/recent'

const date = (ms) => (ms ? new Date(ms).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '')

function counts(sections, notes) {
  if (typeof sections !== 'number' || typeof notes !== 'number') return ''
  return `${sections} ${sections === 1 ? 'section' : 'sections'}, ${notes} ${notes === 1 ? 'note' : 'notes'}`
}

function Example({ example }) {
  return (
    <li className="lib-row">
      <div className="lib-row-main">
        <div className="badges">
          <span className="badge badge-sticker">Pre-generated example</span>
          {example.judged ? <span className="badge">Source-checked</span> : <span className="badge badge-peach">Not judged</span>}
        </div>
        <h4 className="lib-row-title">{example.title}</h4>
        <p className="lib-meta">{[counts(example.sections, example.notes), example.credit].filter(Boolean).join(' · ')}</p>
        {!example.judged && (
          <p className="lib-meta">This run had no judge step, so its notes are not source-checked.</p>
        )}
      </div>
      <Link href={`/app/job/${example.id}`} className="story-button story-button-forest story-button-small w-full">
        Open
      </Link>
    </li>
  )
}

const STATUS = { done: 'Done', running: 'Running', queued: 'Running', error: 'Failed' }

function Row({ entry, live }) {
  const expired = live?.state === 'expired'
  const offline = live?.state === 'offline'
  const status = live?.status || entry.status
  const known = counts(entry.sections, entry.statements)
  let badge = <span className="badge">Checking…</span>
  if (expired) badge = <span className="badge badge-warn">Expired</span>
  else if (live?.state === 'live' || offline) badge = <span className={`badge ${status === 'error' ? 'badge-warn' : ''}`}>{STATUS[status] || status}</span>

  return (
    <li className="lib-row">
      <div className="lib-row-main">
        <div className="badges">{badge}</div>
        <h4 className="lib-row-title">{entry.name || entry.id}</h4>
        <p className="lib-meta">{[date(entry.createdAt), known].filter(Boolean).join(' · ')}</p>
        {expired && (
          <p className="lib-meta">
            The server no longer has this lecture (it may have restarted).{known ? ' The numbers above are what this browser saw last time.' : ''}
          </p>
        )}
        {offline && <p className="lib-meta">Can&apos;t reach the server right now. The numbers above may be old.</p>}
      </div>
      {!expired && (
        <Link href={`/app/job/${entry.id}`} className="story-button story-button-outline story-button-small w-full">
          Open
        </Link>
      )}
    </li>
  )
}

// A private deck on THIS machine only: frontend/public/local-only/ is git-ignored, so the files and manifest.json never reach the repo
// or the deployed site. The page asks for the manifest only on a local address; if it is missing or not valid, nothing is shown.
const LOCAL_MANIFEST = `${LOCAL_DIR}manifest.json`
const fileName = (value) => typeof value === 'string' && /^[\w.-]+$/.test(value)
const count = (value) => typeof value === 'number' && Number.isFinite(value) && value >= 0

function readLocalCopy(data) {
  const ok = data && typeof data.title === 'string' && fileName(data.deck) && fileName(data.notes) && [data.lectures, data.minutes, data.sections, data.statements, data.sourceChecked, data.notJudged].every(count)
  return ok ? data : null
}

function useLocalCopy() {
  const [copy, setCopy] = useState(null)
  useEffect(() => {
    if (!isLocalHost()) return
    let cancelled = false
    fetch(LOCAL_MANIFEST, { cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled) setCopy(readLocalCopy(data))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])
  return copy
}

// The chip says only what the numbers say: a deck with some statements not judged is never called source-checked as a whole.
function judgedChip({ sourceChecked, notJudged }) {
  if (notJudged === 0) return 'Source-checked'
  if (sourceChecked === 0) return 'Not judged'
  return `Mixed: ${sourceChecked} source-checked, ${notJudged} not judged`
}

function LocalCopy({ copy }) {
  return (
    <ul className="lib-grid">
      <li className="lib-row">
        <div className="lib-row-main">
          <div className="badges">
            <span className="badge badge-sticker">Local copy</span>
            <span className="badge badge-peach">{judgedChip(copy)}</span>
          </div>
          <h4 className="lib-row-title">{copy.title}</h4>
          <p className="lib-meta">
            {[copy.date, `${copy.lectures} lectures`, `${copy.minutes} minutes`, `${copy.sections} sections`, `${copy.statements} statements`].filter(Boolean).join(' · ')}
          </p>
          <p className="lib-meta">Only on this computer. It is not uploaded and not part of the site.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href="/app/job/local-course" className="story-button story-button-forest story-button-small">
            Open
          </Link>
          <a href={LOCAL_DIR + copy.deck} download className="story-button story-button-outline story-button-small">
            Download deck (.pptx)
          </a>
          <a href={LOCAL_DIR + copy.notes} download className="story-button story-button-outline story-button-small">
            Download notes (.md)
          </a>
        </div>
      </li>
    </ul>
  )
}

const NOTE = 'Transcripts (.txt, .srt, .vtt). Audio needs a local GPU.'

function StartButton({ large = false }) {
  return (
    <Link href="/app/new" className={`story-button story-button-coral ${large ? '!min-h-[60px] px-8 text-lg' : 'story-button-small'}`}>
      <span aria-hidden="true">+</span> Start your own lecture
    </Link>
  )
}

export default function LibraryView({ photo = false }) {
  const stored = useRecentJobs() // null until mounted
  const localCopy = useLocalCopy()
  const recent = stored || []
  const [live, setLive] = useState({}) // id -> { state: 'live' | 'expired' | 'offline', status }
  const ids = JSON.stringify(recent.map((entry) => entry.id)) // a stable key: the effect runs again only when the set of ids changes

  // Ask the server about every row (at most 20). A 404 means the job is gone: the row says "expired", never a broken page.
  useEffect(() => {
    let cancelled = false
    for (const id of JSON.parse(ids)) {
      getJob(id)
        .then((job) => {
          if (cancelled) return
          setLive((current) => ({ ...current, [id]: { state: 'live', status: job.status } }))
          updateRecent(id, job.status === 'done' ? { status: job.status, sections: job.sections?.length, statements: job.statements?.length } : { status: job.status })
        })
        .catch((error) => {
          if (cancelled) return
          setLive((current) => ({ ...current, [id]: { state: error.status === 404 ? 'expired' : 'offline' } }))
        })
    }
    return () => {
      cancelled = true
    }
  }, [ids])

  return (
    <div className="flex flex-col">
      <div className="lib-head">
        <p className="handwritten lib-label">your lectures</p>
        <Link href="/app/how" className="story-link">
          How it works <span aria-hidden="true">↗</span>
        </Link>
      </div>
      <h2 className="sr-only">Library</h2>

      <section className="lib-hero" style={photo ? { '--hero-photo': 'url(/hero-library.jpg)' } : undefined} aria-labelledby="hero-heading">
        <p className="lib-hero-eyebrow">Your lectures. With receipts.</p>
        <h3 id="hero-heading" className="lib-hero-title">
          Your next lecture,
          <br />
          <em>with receipts.</em>
        </h3>
        <p className="lib-hero-lede">Turn a lecture transcript into notes and slides where every line cites a timestamp or a link.</p>
        <div className="lib-hero-actions">
          <StartButton large />
          <Link href="/app/job/example-strang" className="lib-hero-link">
            See the example <span aria-hidden="true">→</span>
          </Link>
        </div>
        <p className="lib-hero-note">
          <span aria-hidden="true" />
          No account needed. Your list stays in this browser.
        </p>
      </section>

      <section className="lib-section" aria-labelledby="examples-heading">
        <h3 id="examples-heading" className="text-2xl">
          Examples (pre-generated)
        </h3>
        <p className="mt-1 text-muted-foreground">Always available. They open without the server and were written before you came.</p>
        <ul className="lib-grid">
          {EXAMPLES.map((example) => (
            <Example key={example.id} example={example} />
          ))}
        </ul>
      </section>

      <section className="lib-section" aria-labelledby="recent-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 id="recent-heading" className="text-2xl">
            Your lectures
          </h3>
          <button type="button" onClick={clearRecent} disabled={recent.length === 0} className="story-button story-button-outline story-button-small">
            Clear list
          </button>
        </div>
        {localCopy && <LocalCopy copy={localCopy} />}
        {stored === null ? (
          <p role="status" className="mt-5 text-muted-foreground">
            Loading your list…
          </p>
        ) : recent.length === 0 ? (
          <div className="story-panel mt-5 flex flex-col items-start gap-4 !p-6">
            <p>Nothing here yet. Lectures you start on this device show up in this list (the last 20).</p>
            <StartButton />
            <p className="text-sm text-muted-foreground">{NOTE}</p>
          </div>
        ) : (
          <>
            <ul className="lib-grid">
              {recent.map((entry) => (
                <Row key={entry.id} entry={entry} live={live[entry.id]} />
              ))}
            </ul>
            <p className="mt-5 text-sm text-muted-foreground">
              The list lives only in this browser. Clearing it does not delete anything on the server.
            </p>
          </>
        )}
      </section>
    </div>
  )
}
