'use client'

import { useEffect, useState } from 'react'
import { API_URL } from '../lib/api'
import { useAfter } from '../lib/hooks'

// Is the backend answering? The free Render plan sleeps and needs about 30 s to wake up.
export default function HealthStatus() {
  const [phase, setPhase] = useState('checking') // checking | ready | down
  const [attempt, setAttempt] = useState(0)
  const waking = useAfter(phase === 'checking', 6000)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_URL}/health`, { cache: 'no-store' })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(() => !cancelled && setPhase('ready'))
      .catch(() => !cancelled && setPhase('down'))
    return () => {
      cancelled = true
    }
  }, [attempt])

  const text =
    phase === 'ready'
      ? 'Server ready'
      : phase === 'down'
        ? "Can't reach the server."
        : waking
          ? 'The server is waking up. The first request on the free plan can take about 30 seconds.'
          : 'Checking the server…'
  const dot = phase === 'ready' ? 'bg-coral' : phase === 'down' ? 'bg-destructive' : 'bg-control'

  return (
    <p role="status" className="flex flex-wrap items-center gap-x-2">
      <span aria-hidden className={`inline-block h-2.5 w-2.5 rounded-full ${dot}`} />
      <span>{text}</span>
      {phase === 'down' && (
        <button
          type="button"
          onClick={() => {
            setPhase('checking')
            setAttempt((n) => n + 1)
          }}
          className="story-link cursor-pointer"
        >
          Try again
        </button>
      )}
    </p>
  )
}
