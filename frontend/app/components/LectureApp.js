'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { createJob, createSampleJob, describeError, describeJobFailure, getJob } from '../lib/api'
import ErrorNotice from './ErrorNotice'
import UploadBox from './UploadBox'
import ProgressView from './ProgressView'
import ResultsView from './ResultsView'

const POLL_MS = 2000
const MAX_POLL_FAILURES = 5
const STORAGE_KEY = 'voice2text.jobId'

function remember(id) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {}
}

export default function LectureApp() {
  const [job, setJob] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const failures = useRef(0)
  const jobId = job?.id
  const finished = job && (job.status === 'done' || job.status === 'error')

  // Come back to a job after a page reload.
  useEffect(() => {
    let saved = null
    try {
      saved = localStorage.getItem(STORAGE_KEY)
    } catch {}
    if (!saved) return
    getJob(saved)
      .then(setJob)
      .catch(() => remember(null))
  }, [])

  // Poll the job until it is done or failed.
  useEffect(() => {
    if (!jobId || finished) return
    const timer = setInterval(async () => {
      try {
        setJob(await getJob(jobId))
        failures.current = 0
        setError(null)
      } catch (e) {
        failures.current += 1
        if (e.status === 404 || failures.current >= MAX_POLL_FAILURES) {
          setError(describeError(e))
          setJob(null)
          remember(null)
        }
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [jobId, finished])

  const [lastAction, setLastAction] = useState(null) // what "Try again" repeats
  const start = useCallback(async (create) => {
    setLastAction(() => create)
    setBusy(true)
    setError(null)
    failures.current = 0
    try {
      const created = await create()
      remember(created.id)
      setJob(created)
    } catch (e) {
      setError(describeError(e))
    } finally {
      setBusy(false)
    }
  }, [])

  function reset() {
    remember(null)
    setJob(null)
    setError(null)
  }

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <ErrorNotice {...error} onRetry={lastAction ? () => start(lastAction) : reset} onSecondary={reset} secondaryLabel="Start over" />
      )}
      {!job && <UploadBox busy={busy} onFile={(file) => start(() => createJob(file))} onSample={() => start(createSampleJob)} />}
      {job && job.status !== 'done' && (
        <>
          <ProgressView job={job} />
          {job.status === 'error' && (
            <ErrorNotice {...describeJobFailure(job)} onRetry={reset} />
          )}
        </>
      )}
      {job && job.status === 'done' && <ResultsView job={job} onReset={reset} />}
    </div>
  )
}
