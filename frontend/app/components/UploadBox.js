'use client'

import { useRef, useState } from 'react'
import { checkFile, ALLOWED_EXTENSIONS, MAX_UPLOAD_MB } from '../lib/api'

export default function UploadBox({ onFile, onSample, busy }) {
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
    <div className="flex flex-col gap-4">
      <div
        role="button"
        tabIndex={0}
        onClick={() => !busy && input.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && !busy && input.current?.click()}
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
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-10 text-center transition ${
          dragging ? 'border-blue-500 bg-blue-500/10' : 'border-zinc-400 hover:border-blue-500 dark:border-zinc-600'
        } ${busy ? 'cursor-wait opacity-60' : ''}`}
      >
        <p className="text-lg font-medium">Drop a lecture recording here, or click to choose</p>
        <p className="text-sm text-zinc-500">
          Audio or video ({ALLOWED_EXTENSIONS.slice(0, 4).join(', ')}, ...) or a transcript (.txt, .srt, .vtt). Up to {MAX_UPLOAD_MB} MB.
        </p>
        <input
          ref={input}
          type="file"
          className="hidden"
          accept={ALLOWED_EXTENSIONS.join(',')}
          onChange={(e) => {
            pick(e.target.files?.[0])
            e.target.value = ''
          }}
        />
      </div>
      {problem && (
        <p role="alert" className="text-sm text-red-600">
          {problem}
        </p>
      )}
      <button
        type="button"
        onClick={onSample}
        disabled={busy}
        className="self-start rounded-lg border border-zinc-400 px-4 py-2 text-sm font-medium hover:bg-zinc-500/10 disabled:opacity-50 dark:border-zinc-600"
      >
        Try a sample lecture
      </button>
    </div>
  )
}
