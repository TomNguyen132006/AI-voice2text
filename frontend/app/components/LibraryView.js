'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { getJob } from '../lib/api'
import { EXAMPLES } from '../lib/examples'
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
          {!example.judged && <span className="badge badge-peach">Not judged</span>}
        </div>
        <h4 className="lib-row-title">{example.title}</h4>
        <p className="lib-meta">{[counts(example.sections, example.notes), example.credit].filter(Boolean).join(' · ')}</p>
        {!example.judged && (
          <p className="lib-meta">This run had no judge step, so its notes are not source-checked.</p>
        )}
      </div>
      <Link href={`/app/job/${example.id}`} className="story-button story-button-forest story-button-small w-full sm:w-auto">
        Open example
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
        <Link href={`/app/job/${entry.id}`} className="story-button story-button-outline story-button-small w-full sm:w-auto">
          Open
        </Link>
      )}
    </li>
  )
}

export default function LibraryView() {
  const stored = useRecentJobs() // null until mounted
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
      <div>
        <p className="handwritten">your lectures</p>
        <h2 className="text-4xl leading-tight">Library</h2>
      </div>

      <section className="lib-section" aria-labelledby="examples-heading">
        <h3 id="examples-heading" className="text-2xl">
          Examples (pre-generated)
        </h3>
        <p className="mt-1 text-muted-foreground">Always available. They open without the server and were written before you came.</p>
        <ul className="lib-list">
          {EXAMPLES.map((example) => (
            <Example key={example.id} example={example} />
          ))}
        </ul>
      </section>

      <section className="lib-section" aria-labelledby="recent-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 id="recent-heading" className="text-2xl">
            Recent lectures in this browser
          </h3>
          <button type="button" onClick={clearRecent} disabled={recent.length === 0} className="story-button story-button-outline story-button-small">
            Clear list
          </button>
        </div>
        {stored === null ? (
          <p role="status" className="mt-5 text-muted-foreground">
            Loading your list…
          </p>
        ) : recent.length === 0 ? (
          <div className="story-panel mt-5 flex flex-col items-start gap-4 !p-6">
            <p>Nothing here yet. Lectures you start on this device show up in this list (the last 20).</p>
            <Link href="/app/new" className="story-button story-button-coral story-button-small">
              New lecture
            </Link>
          </div>
        ) : (
          <>
            <ul className="lib-list">
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
