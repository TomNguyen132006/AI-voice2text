'use client'

import { useCallback, useEffect, useReducer, useState, useSyncExternalStore } from 'react'
import { createJob, createSampleJob, describeError, describeJobFailure, getJob } from '../lib/api'
import { useAfter } from '../lib/hooks'
import ErrorNotice from './ErrorNotice'
import ProgressView from './ProgressView'
import ResultsView from './ResultsView'
import { HowItWorks, Values } from './Landing'
import UploadBox from './UploadBox'

const POLL_MS = 2000
const LOST_AFTER = 8 // this many failed polls in a row: say that the server cannot be reached
const STORAGE_KEY = 'voice2text.jobId'

function remember(id) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {}
}

// The id of the last job, so a reload comes back to it. The server renders the start screen (null).
function readSaved() {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}
const noSubscription = () => () => {}

// job: the last answer of GET /jobs/{id}. log: when this browser saw each stage begin and end (ms),
// because the API only says which stage is current.
function reducer(state, action) {
  if (action.type === 'reset') return { job: null, log: {} }
  const { job, at } = action
  const log = job.id === state.job?.id ? { ...state.log } : {}
  const before = state.job?.id === job.id ? state.job.stage : null
  if (job.stage !== before) {
    if (before && log[before] && !log[before].end) log[before] = { ...log[before], end: at }
    if (job.status === 'running' || job.status === 'queued') log[job.stage] = { start: at }
  }
  if (job.status === 'done' || job.status === 'error') {
    for (const key of Object.keys(log)) if (!log[key].end) log[key] = { ...log[key], end: at }
  }
  return { job, log }
}

function Loading() {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-4">
      <h2 className="text-3xl">Loading your notes…</h2>
      <div aria-hidden className="flex animate-pulse flex-col gap-3">
        <div className="h-5 w-2/3 rounded-full bg-accent" />
        <div className="h-5 w-full rounded-full bg-accent" />
        <div className="h-5 w-5/6 rounded-full bg-accent" />
      </div>
    </div>
  )
}

// A job (running, failed or done) lives in one calm column; the start page has the hero.
function Column({ children }) {
  return (
    <main id="story-main" tabIndex={-1} className="story-column py-8 pb-16">
      {children}
    </main>
  )
}

export default function LectureApp() {
  const [{ job, log }, dispatch] = useReducer(reducer, { job: null, log: {} })
  const savedId = useSyncExternalStore(noSubscription, readSaved, () => null)
  const [restored, setRestored] = useState(false) // the first look at the saved job is over
  const [busy, setBusy] = useState(false)
  const [fileName, setFileName] = useState('')
  const [error, setError] = useState(null)
  const [lastAction, setLastAction] = useState(null) // what "Try again" repeats
  const [failures, setFailures] = useState(0)
  const [tick, setTick] = useState(0) // "Try again" while the server cannot be reached
  const jobId = job?.id
  const finished = job && (job.status === 'done' || job.status === 'error')
  const lost = failures >= LOST_AFTER
  const restoring = Boolean(savedId) && !job && !restored
  // The server is slow to answer: asleep (free plan) or still starting. Shown after 6 s of waiting, or as soon as a poll fails.
  const waking = useAfter(busy, 6000) || (Boolean(jobId) && !finished && failures > 0)

  // Come back to a job after a page reload.
  useEffect(() => {
    if (!savedId) return
    let cancelled = false
    getJob(savedId)
      .then((saved) => !cancelled && dispatch({ type: 'job', job: saved, at: Date.now() }))
      .catch(() => !cancelled && remember(null))
      .finally(() => !cancelled && setRestored(true))
    return () => {
      cancelled = true
    }
  }, [savedId])

  // Ask for the job until it is done or failed, then stop.
  useEffect(() => {
    if (!jobId || finished) return
    let cancelled = false
    async function poll() {
      try {
        const latest = await getJob(jobId)
        if (cancelled) return
        dispatch({ type: 'job', job: latest, at: Date.now() })
        setFailures(0)
      } catch (e) {
        if (cancelled) return
        if (e.status === 404) {
          remember(null)
          dispatch({ type: 'reset' })
          setError(describeError(e))
        } else {
          setFailures((n) => n + 1)
        }
      }
    }
    poll()
    const timer = setInterval(poll, lost ? POLL_MS * 3 : POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [jobId, finished, lost, tick])

  const start = useCallback(async (create, name = '') => {
    setLastAction({ create, name })
    setFileName(name)
    setBusy(true)
    setError(null)
    setFailures(0)
    try {
      const created = await create()
      remember(created.id)
      dispatch({ type: 'job', job: created, at: Date.now() })
    } catch (e) {
      setError(describeError(e))
    } finally {
      setBusy(false)
    }
  }, [])

  function reset() {
    remember(null)
    dispatch({ type: 'reset' })
    setError(null)
    setFailures(0)
  }

  if (restoring) {
    return (
      <Column>
        <Loading />
      </Column>
    )
  }
  if (job && job.status === 'done') {
    return (
      <Column>
        <ResultsView job={job} onReset={reset} />
      </Column>
    )
  }

  if (job) {
    return (
      <Column>
        <div className="flex flex-col gap-6">
          <ProgressView job={job} log={log} waking={waking} />
          {job.status === 'error' && <ErrorNotice {...describeJobFailure(job)} onRetry={reset} />}
          {lost && job.status !== 'error' && (
            <ErrorNotice
              {...describeError({ kind: 'network' })}
              onRetry={() => {
                setFailures(0)
                setTick((n) => n + 1)
              }}
              onSecondary={reset}
              secondaryLabel="Start over"
            />
          )}
        </div>
      </Column>
    )
  }

  return (
    <main id="story-main" tabIndex={-1}>
      <section className="story-hero story-wrap" aria-labelledby="hero-title">
        <div className="story-hero-copy">
          <p className="handwritten">notes with receipts ✦</p>
          <h1 id="hero-title">
            Your lecture, turned into notes <span className="marker">you can check.</span>
          </h1>
          <p className="story-lede">
            Upload a lecture transcript or recording. You get notes, slides and sources, with every line tied to a timestamp or a link.
          </p>
          <p className="hero-note">
            <strong>Source-checked</strong> means the cited source supports the statement. It does not check that the source itself is true.
          </p>
        </div>
        <div className="story-hero-art">
          <span className="story-sticker hero-sticker" aria-hidden="true">
            source-checked
          </span>
          <div className="story-panel">
            <UploadBox
              busy={busy}
              fileName={fileName}
              waking={waking && busy}
              onFile={(file) => start(() => createJob(file), file.name)}
              onSample={() => start(createSampleJob)}
              notice={
                error && (
                  <ErrorNotice
                    {...error}
                    onRetry={lastAction ? () => start(lastAction.create, lastAction.name) : reset}
                    onSecondary={lastAction ? reset : undefined}
                    secondaryLabel="Start over"
                  />
                )
              }
            />
          </div>
        </div>
      </section>
      <Values />
      <HowItWorks />
    </main>
  )
}
