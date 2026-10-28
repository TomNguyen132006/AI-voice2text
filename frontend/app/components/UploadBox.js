'use client'

import { useRef, useState } from 'react'
import { ALLOWED_EXTENSIONS, MAX_TRANSCRIPT_CHARS, MAX_UPLOAD_MB, checkFile } from '../lib/api'

function UploadIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </svg>
  )
}

// Start screen: pick a transcript (or the sample). Audio is still sent to the server, which answers 400 when it has no GPU,
// and that answer is shown as a friendly message (see describeError).
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
    <section aria-labelledby="start-heading" className="flex flex-col gap-6">
      <h2 id="start-heading" className="sr-only">
        Start
      </h2>
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
        className={`flex min-h-56 cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors focus-within:outline-3 focus-within:outline-offset-2 focus-within:outline-accent ${
          dragging ? 'border-accent bg-accent-soft' : 'border-line-strong bg-surface hover:border-accent'
        } ${busy ? 'cursor-wait opacity-70' : ''}`}
      >
        <span className="text-accent">
          <UploadIcon />
        </span>
        <span className="font-read text-xl font-semibold text-navy">
          {busy ? `Uploading ${fileName || 'your file'}…` : 'Drop a transcript here'}
        </span>
        {!busy && (
          <span className="btn btn-primary" aria-hidden>
            Choose a file
          </span>
        )}
        <span className="text-muted">.txt, .srt or .vtt</span>
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
        <p role="status" className="rounded-lg border border-accent/30 bg-accent-soft px-4 py-3 text-accent-ink">
          The server is waking up. On the free plan the first request can take about 30 seconds.
        </p>
      )}
      {problem && (
        <p role="alert" className="rounded-lg border border-danger/40 bg-danger-soft px-4 py-3 text-danger">
          {problem}
        </p>
      )}
      {notice}
      <dl className="grid gap-x-6 gap-y-3 text-muted sm:grid-cols-[auto_1fr]">
        <dt className="font-semibold text-ink">Limits</dt>
        <dd>
          {MAX_UPLOAD_MB} MB and {MAX_TRANSCRIPT_CHARS.toLocaleString('en-US')} characters, about 20 minutes of speech. A 4-minute lecture took about 4 minutes to process.
        </dd>
        <dt className="font-semibold text-ink">Audio</dt>
        <dd>Audio files (.mp3, .wav, .mp4 and so on) work only on a server with a GPU. If this one has none, you will be asked for a transcript.</dd>
      </dl>
      <div className="flex flex-col gap-3 border-t border-line pt-6 sm:flex-row sm:items-center sm:gap-4">
        <button type="button" onClick={onSample} disabled={busy} className="btn btn-secondary w-full sm:w-auto">
          Try the sample
        </button>
        <p className="text-muted">Short hand-written data to show the layout. No model is called.</p>
      </div>
    </section>
  )
}
