'use client'

import { useEffect, useState } from 'react'

/** True once `active` has been true for `ms` milliseconds. Used for "the server is waking up" lines. */
export function useAfter(active, ms) {
  const [late, setLate] = useState(false)
  useEffect(() => {
    if (!active) return
    const timer = setTimeout(() => setLate(true), ms)
    return () => {
      clearTimeout(timer)
      setLate(false)
    }
  }, [active, ms])
  return active && late
}

/** The current time in ms, refreshed every `ms` while `active` (0 until the first tick). */
export function useNow(active, ms = 1000) {
  const [now, setNow] = useState(0)
  useEffect(() => {
    if (!active) return
    const tick = () => setNow(Date.now())
    const first = setTimeout(tick, 0)
    const timer = setInterval(tick, ms)
    return () => {
      clearTimeout(first)
      clearInterval(timer)
    }
  }, [active, ms])
  return now
}
