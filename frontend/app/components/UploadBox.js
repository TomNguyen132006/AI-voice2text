'use client'

import { useRef, useState } from 'react'
import { ALLOWED_EXTENSIONS, MAX_UPLOAD_MB, checkFile } from '../lib/api'

// Start screen: pick a transcript (or the sample). Audio is still sent to the server, which answers 400 when it has no GPU.
export default function UploadBox({ busy, fileName, onFile, onSample }) {
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
        className={`flex min-h-44 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors focus-within:outline-3 focus-within:outline-offset-2 focus-within:outline-accent ${
          dragging ? 'border-accent bg-accent-soft' : 'border-line-strong bg-surface hover:border-accent'
        } ${busy ? 'cursor-wait opacity-70' : ''}`}
      >
        <span className="text-lg font-medium">{busy ? `Uploading ${fileName || 'your file'}…` : 'Drop a transcript here, or choose a file'}</span>
        <span className="text-muted">.txt, .srt or .vtt, up to {MAX_UPLOAD_MB} MB</span>
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
      {problem && (
        <p role="alert" className="rounded-lg border border-danger/40 bg-danger-soft px-4 py-3 text-danger">
          {problem}
        </p>
      )}
      <ul className="list-disc space-y-1 pl-5 text-muted">
        <li>There is no length limit. In our test, a 4-minute lecture took about 4 minutes to process.</li>
        <li>Audio (.mp3, .wav, .mp4 and so on) is accepted only by a server with a GPU. If this one has none, you will be asked for a transcript.</li>
      </ul>
      <div className="flex flex-col gap-2 border-t border-line pt-6 sm:flex-row sm:items-center sm:gap-4">
        <button
          type="button"
          onClick={onSample}
          disabled={busy}
          className="w-full rounded-lg border border-accent px-5 py-2.5 font-medium text-accent hover:bg-accent-soft disabled:opacity-50 sm:w-auto"
        >
          Try the sample
        </button>
        <p className="text-muted">Short hand-written data to show the layout. No model is called.</p>
      </div>
    </section>
  )
}
