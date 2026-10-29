'use client'

import { useParams, useRouter } from 'next/navigation'
import { useEffect, useReducer, useState } from 'react'
import { describeError, describeJobFailure, getJob } from '../lib/api'
import { findExample } from '../lib/examples'
import { useAfter } from '../lib/hooks'
import { jobReducer } from '../lib/jobReducer'
import { updateRecent } from '../lib/recent'
import ErrorNotice from './ErrorNotice'
import ProgressView from './ProgressView'
import ResultsView from './ResultsView'

const POLL_MS = 2000
const LOST_AFTER = 8 // this many failed polls in a row: say that the server cannot be reached

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

// A pre-generated example: one static JSON file, no backend call.
function ExampleJob({ example }) {
  const router = useRouter()
  const [job, setJob] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let cancelled = false
    fetch(example.json)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error('missing'))))
      .then((data) => !cancelled && setJob(data))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [example.json])
  if (failed) {
    return (
      <ErrorNotice
        title="The example did not load"
        message="The file could not be read. Check your connection and try again."
        onRetry={() => window.location.reload()}
        retryLabel="Reload"
        onSecondary={() => router.replace('/app/library')}
        secondaryLabel="Back to library"
      />
    )
  }
  if (!job) return <Loading />
  return <ResultsView job={job} example={example} onReset={() => router.push('/app/new')} />
}

// A live job: ask the server every 2 s until it is done or failed. A 404 (the server restarted) is a message with a way out.
function LiveJob({ id }) {
  const router = useRouter()
  const [{ job, log }, dispatch] = useReducer(jobReducer, { job: null, log: {} })
  const [missing, setMissing] = useState(false)
  const [failures, setFailures] = useState(0)
  const [tick, setTick] = useState(0) // "Try again" while the server cannot be reached
  const finished = job && (job.status === 'done' || job.status === 'error')
  const lost = failures >= LOST_AFTER
  const waking = useAfter(!job && !missing, 6000) || (!finished && failures > 0)

  useEffect(() => {
    if (finished || missing) return
    let cancelled = false
    async function poll() {
      try {
        const latest = await getJob(id)
        if (cancelled) return
        dispatch({ type: 'job', job: latest, at: Date.now() })
        setFailures(0)
      } catch (e) {
        if (cancelled) return
        if (e.status === 404) setMissing(true)
        else setFailures((n) => n + 1)
      }
    }
    poll()
    const timer = setInterval(poll, lost ? POLL_MS * 3 : POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [id, finished, missing, lost, tick])

  // A lecture the server no longer has must not stay as the "last lecture" of the Resume link.
  useEffect(() => {
    if (!missing) return
    try {
      if (localStorage.getItem('voice2text.jobId') === id) localStorage.removeItem('voice2text.jobId')
    } catch {}
  }, [missing, id])

  // Keep the library row up to date (status and counts), so it can still say something after the server forgets the job.
  const status = job?.status
  const sectionCount = job?.sections?.length
  const statementCount = job?.statements?.length
  useEffect(() => {
    if (!status) return
    updateRecent(id, status === 'done' ? { status, sections: sectionCount, statements: statementCount } : { status })
  }, [id, status, sectionCount, statementCount])

  if (missing) {
    return (
      <ErrorNotice
        {...describeError({ status: 404 })}
        message="The server may have restarted and lost this lecture. Upload the file again to get new notes."
        onRetry={() => router.push('/app/new')}
        retryLabel="New lecture"
        onSecondary={() => router.replace('/app/library')}
        secondaryLabel="Back to library"
      />
    )
  }
  if (!job) return <Loading />
  if (job.status === 'done') return <ResultsView job={job} onReset={() => router.push('/app/new')} />
  return (
    <div className="flex flex-col gap-6">
      <ProgressView job={job} log={log} waking={waking} />
      {job.status === 'error' && <ErrorNotice {...describeJobFailure(job)} onRetry={() => router.push('/app/new')} retryLabel="New lecture" />}
      {lost && job.status !== 'error' && (
        <ErrorNotice
          {...describeError({ kind: 'network' })}
          onRetry={() => {
            setFailures(0)
            setTick((n) => n + 1)
          }}
          onSecondary={() => router.replace('/app/library')}
          secondaryLabel="Back to library"
        />
      )}
    </div>
  )
}

export default function JobView() {
  const { id } = useParams()
  const example = findExample(id)
  return example ? <ExampleJob example={example} /> : <LiveJob id={decodeURIComponent(id)} />
}
