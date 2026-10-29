'use client'

import { useMemo, useSyncExternalStore } from 'react'

// The list of lectures this browser started: [{ id, name, createdAt, status, sections, statements }].
// Only this browser has it (localStorage); the server forgets jobs when it restarts, so a row can be "expired".
export const RECENT_KEY = 'lecturesque.recentJobs'
export const RECENT_MAX = 20
const CHANGED = 'lecturesque:recent'

function read() {
  try {
    return localStorage.getItem(RECENT_KEY)
  } catch {
    return null
  }
}

function parse(raw) {
  try {
    const list = JSON.parse(raw || '[]')
    return Array.isArray(list) ? list.filter((e) => e && typeof e.id === 'string').slice(0, RECENT_MAX) : []
  } catch {
    return []
  }
}

function write(list) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX)))
  } catch {}
  window.dispatchEvent(new Event(CHANGED))
}

export function addRecent({ id, name }) {
  const rest = parse(read()).filter((e) => e.id !== id)
  write([{ id, name: name || '', createdAt: Date.now(), status: 'queued' }, ...rest])
}

// Merge cached facts (status, counts) into one row. Nothing is written when nothing changed.
export function updateRecent(id, patch) {
  const list = parse(read())
  const entry = list.find((e) => e.id === id)
  if (!entry || Object.entries(patch).every(([key, value]) => entry[key] === value)) return
  write(list.map((e) => (e.id === id ? { ...e, ...patch } : e)))
}

export function clearRecent() {
  write([])
}

function subscribe(callback) {
  window.addEventListener(CHANGED, callback)
  window.addEventListener('storage', callback)
  return () => {
    window.removeEventListener(CHANGED, callback)
    window.removeEventListener('storage', callback)
  }
}

export function useRecentJobs() {
  const raw = useSyncExternalStore(subscribe, read, () => null)
  return useMemo(() => parse(raw), [raw])
}
