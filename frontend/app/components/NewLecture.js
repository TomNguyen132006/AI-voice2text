'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { createJob, createSampleJob, describeError } from '../lib/api'
import { useAfter } from '../lib/hooks'
import { addRecent } from '../lib/recent'
import ErrorNotice from './ErrorNotice'
import UploadBox from './UploadBox'

// The old key, still written so that the start page (/) can bring the last job back after a reload.
const LAST_JOB_KEY = 'voice2text.jobId'

// The upload card inside the app. Same API calls and limits as the start page; on success the job opens at /app/job/{id}.
export default function NewLecture() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [fileName, setFileName] = useState('')
  const [error, setError] = useState(null)
  const [lastAction, setLastAction] = useState(null) // what "Try again" repeats
  const waking = useAfter(busy, 6000)

  async function start(create, name = '') {
    setLastAction({ create, name })
    setFileName(name)
    setBusy(true)
    setError(null)
    try {
      const created = await create()
      addRecent({ id: created.id, name: name || 'Sample (hand-written)' })
      try {
        localStorage.setItem(LAST_JOB_KEY, created.id)
      } catch {}
      router.push(`/app/job/${encodeURIComponent(created.id)}`)
    } catch (e) {
      setError(describeError(e))
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="handwritten">notes with receipts ✦</p>
        <h2 className="text-4xl leading-tight">New lecture</h2>
      </div>
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
                onRetry={lastAction ? () => start(lastAction.create, lastAction.name) : undefined}
                onSecondary={() => setError(null)}
                secondaryLabel="Dismiss"
              />
            )
          }
        />
      </div>
      <p className="text-sm text-muted-foreground">
        <strong className="text-foreground">Source-checked</strong> means the cited source supports the note. It does not check that the source itself is true.
      </p>
    </div>
  )
}
