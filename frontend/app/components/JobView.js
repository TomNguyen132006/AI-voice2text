'use client'

import { useParams, useRouter } from 'next/navigation'
import { useEffect, useReducer, useState } from 'react'
import { describeError, describeJobFailure, getJob } from '../lib/api'
import { findExample } from '../lib/examples'
import { useAfter } from '../lib/hooks'
import { jobReducer } from '../lib/jobReducer'
import { isLocalHost, LOCAL_DIR } from '../lib/localCopy'
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

// A private copy of a course, on this computer only: static files from the git-ignored /local-only/ folder, no backend call.
// Anywhere else (the deployed site, another computer) the file is missing and this is the normal "not found" screen.
const LOCAL_COURSE_ID = 'local-course'

function LocalCourseJob() {
  const router = useRouter()
  const [state, setState] = useState({ job: null, local: null, failed: false })
  useEffect(() => {
    let cancelled = false
    const fail = () => !cancelled && setState({ job: null, local: null, failed: true })
    if (!isLocalHost()) {
      fail()
      return () => {
        cancelled = true
      }
    }
    Promise.all([fetch(`${LOCAL_DIR}course.json`, { cache: 'no-store' }), fetch(`${LOCAL_DIR}manifest.json`, { cache: 'no-store' })])
      .then(async ([course, manifest]) => {
        if (!course.ok || !manifest.ok) return fail()
        const [job, info] = await Promise.all([course.json(), manifest.json()])
        const plain = (name) => typeof name === 'string' && /^[\w.-]+$/.test(name)
        if (!Array.isArray(job?.statements) || !Array.isArray(job?.sections) || !job.summary || !plain(info?.deck) || !plain(info?.notes)) return fail()
        if (!cancelled) setState({ job, local: { deck: info.deck, notes: info.notes }, failed: false })
      })
      .catch(fail)
    return () => {
      cancelled = true
    }
  }, [])
  if (state.failed) {
    return (
      <ErrorNotice
        {...describeError({ status: 404 })}
        message="There is no lecture with this address."
        onSecondary={() => router.replace('/app/library')}
        secondaryLabel="Back to library"
      />
    )
  }
  if (!state.job) return <Loading />
  return <ResultsView job={state.job} local={state.local} onReset={() => router.push('/app/new')} />
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
  if (id === LOCAL_COURSE_ID) return <LocalCourseJob />
  return example ? <ExampleJob example={example} /> : <LiveJob id={decodeURIComponent(id)} />
}
