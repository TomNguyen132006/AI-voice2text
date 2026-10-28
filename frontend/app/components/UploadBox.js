'use client'

import { useRef, useState } from 'react'
import { ALLOWED_EXTENSIONS, MAX_TRANSCRIPT_CHARS, MAX_UPLOAD_MB, checkFile } from '../lib/api'

function UploadIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </svg>
  )
}

// The card on the start page: pick a transcript (or the sample). Audio is still sent to the server, which answers 400 when it
// has no GPU, and that answer is shown as a friendly message (see describeError).
export default function UploadBox({ busy, fileName, waking, notice, onFile, onSample }) {
  const input = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [problem, setProblem] = useState(null)

  function pick(file) {
    if (!file) return
    const message = checkFile(file)
    setProblem(message)
    if (!message) onFile(file)
  }

  return (
    <section aria-labelledby="start-heading" className="flex flex-col gap-5">
      <div>
        <p className="story-label text-muted-foreground">START HERE</p>
        <h2 id="start-heading" className="mt-1 text-3xl">
          Bring a transcript
        </h2>
      </div>
      <label
        htmlFor="transcript-file"
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          if (!busy) pick(e.dataTransfer.files?.[0])
        }}
        className={`dropzone ${dragging ? 'dragging' : ''} ${busy ? 'busy' : ''}`}
      >
        <span className="dropzone-icon">
          <UploadIcon />
        </span>
        <span className="text-lg font-semibold">{busy ? `Uploading ${fileName || 'your file'}…` : 'Drop a transcript here'}</span>
        {!busy && (
          <span className="story-button story-button-coral story-button-small" aria-hidden>
            Choose a file
          </span>
        )}
        <span className="story-label text-muted-foreground">.txt · .srt · .vtt</span>
        <input
          id="transcript-file"
          ref={input}
          type="file"
          className="sr-only"
          disabled={busy}
          accept={ALLOWED_EXTENSIONS.join(',')}
          onChange={(e) => {
            pick(e.target.files?.[0])
            e.target.value = ''
          }}
        />
      </label>
      {busy && waking && (
        <p role="status" className="rounded-2xl bg-accent px-4 py-3 text-accent-foreground">
          The server is waking up. On the free plan the first request can take about 30 seconds.
        </p>
      )}
      {problem && (
        <p role="alert" className="rounded-2xl bg-destructive-soft px-4 py-3 font-medium text-destructive">
          {problem}
        </p>
      )}
      {notice}
      <dl className="grid gap-x-5 gap-y-2 text-[15px] text-muted-foreground sm:grid-cols-[auto_1fr]">
        <dt className="font-semibold text-foreground">Limits</dt>
        <dd>
          {MAX_UPLOAD_MB} MB and {MAX_TRANSCRIPT_CHARS.toLocaleString('en-US')} characters, about 20 minutes of speech. The server says so if a file is over.
        </dd>
        <dt className="font-semibold text-foreground">Audio</dt>
        <dd>Audio (.mp3, .wav, .mp4 and so on) works only on a server with a GPU. If this one has none, you will be asked for a transcript.</dd>
      </dl>
      <div className="flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:gap-4">
        <button type="button" onClick={onSample} disabled={busy} className="story-button story-button-outline story-button-small w-full sm:w-auto">
          Try the sample
        </button>
        <p className="text-[15px] text-muted-foreground">Short hand-written data to show the layout. No model is called.</p>
      </div>
    </section>
  )
}
