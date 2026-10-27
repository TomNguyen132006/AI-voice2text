'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { createJob, createSampleJob, getJob } from '../lib/api'
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
          setError(e.status === 404 ? 'This job no longer exists on the server.' : e.message)
          setJob(null)
          remember(null)
        }
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [jobId, finished])

  const start = useCallback(async (create) => {
    setBusy(true)
    setError(null)
    failures.current = 0
    try {
      const created = await create()
      remember(created.id)
      setJob(created)
    } catch (e) {
      setError(e.message)
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
        <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
      {!job && <UploadBox busy={busy} onFile={(file) => start(() => createJob(file))} onSample={() => start(createSampleJob)} />}
      {job && job.status !== 'done' && (
        <>
          <ProgressView job={job} />
          {job.status === 'error' && (
            <div className="flex flex-col gap-3">
              <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300">
                {job.error}
              </p>
              <button type="button" onClick={reset} className="self-start rounded-lg border border-zinc-400 px-4 py-2 text-sm font-medium dark:border-zinc-600">
                Try another file
              </button>
            </div>
          )}
        </>
      )}
      {job && job.status === 'done' && <ResultsView job={job} onReset={reset} />}
    </div>
  )
}
