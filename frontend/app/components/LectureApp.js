'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { createSampleJob, describeError } from '../lib/api'
import { useAfter } from '../lib/hooks'
import { addRecent } from '../lib/recent'
import ErrorNotice from './ErrorNotice'
import { HowItWorks, Values } from './Landing'
import ResumeLink from './ResumeLink'

// The old key, still written so the "Resume your last lecture" link has something to point at.
const LAST_JOB_KEY = 'voice2text.jobId'

function Arrow() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  )
}

// The start page. Nothing is uploaded here: the upload lives at /app/new, a job at /app/job/[id].
export default function LectureApp() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const waking = useAfter(busy, 6000)

  // The sample: same API call as before. replace, so browser Back from the job does not come back to this click.
  async function trySample() {
    setBusy(true)
    setError(null)
    try {
      const created = await createSampleJob()
      addRecent({ id: created.id, name: 'Sample (hand-written)' })
      try {
        localStorage.setItem(LAST_JOB_KEY, created.id)
      } catch {}
      router.replace(`/app/job/${encodeURIComponent(created.id)}`)
    } catch (e) {
      setError(describeError(e))
      setBusy(false)
    }
  }

  return (
    <main id="story-main" tabIndex={-1}>
      <section className="story-hero story-wrap" aria-labelledby="hero-title">
        <div className="story-hero-copy">
          <p className="handwritten">notes with receipts ✦</p>
          <h1 id="hero-title">
            Your lecture, turned into notes <span className="marker">you can check.</span>
          </h1>
          <p className="story-lede">Upload a lecture transcript. You get notes, slides and sources, with every line tied to a timestamp or a link.</p>
          <p className="hero-note">
            <strong>Source-checked</strong> means the cited source supports the statement. It does not check that the source itself is true.
          </p>
          <ResumeLink />
        </div>
        <div className="story-hero-art">
          <span className="story-sticker hero-sticker" aria-hidden="true">
            source-checked
          </span>
          <div className="story-panel">
            <section aria-labelledby="start-heading" className="flex flex-col gap-5">
              <div>
                <p className="story-label text-muted-foreground">START HERE</p>
                <h2 id="start-heading" className="sr-only">
                  Start
                </h2>
              </div>
              <Link href="/app/new" className="story-button story-button-coral w-full !min-h-[60px] text-lg">
                Start your own lecture
                <Arrow />
              </Link>
              <div className="flex flex-col gap-3 sm:flex-row">
                <Link href="/app/job/example-strang" className="story-button story-button-outline story-button-small w-full sm:w-auto">
                  See an example
                </Link>
                <button type="button" onClick={trySample} disabled={busy} className="story-button story-button-outline story-button-small w-full sm:w-auto">
                  {busy ? 'Opening the sample…' : 'Try the sample'}
                </button>
              </div>
              {busy && waking && (
                <p role="status" className="rounded-2xl bg-accent px-4 py-3 text-accent-foreground">
                  The server is waking up. On the free plan the first request can take about 30 seconds.
                </p>
              )}
              {error && <ErrorNotice {...error} onRetry={trySample} onSecondary={() => setError(null)} secondaryLabel="Dismiss" />}
              <p className="text-[15px] text-muted-foreground">Transcripts (.txt, .srt, .vtt). Audio needs a local GPU.</p>
            </section>
          </div>
        </div>
      </section>
      <Values />
      <HowItWorks />
    </main>
  )
}
