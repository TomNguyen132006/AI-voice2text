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

// One stored entry, with every field checked: anything else in localStorage (old versions, hand edits, a failed write)
// must never reach the page. An entry without a string id is skipped.
function clean(entry) {
  if (!entry || typeof entry !== 'object' || typeof entry.id !== 'string' || !entry.id) return null
  const count = (value) => (typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : undefined)
  return {
    id: entry.id,
    name: typeof entry.name === 'string' ? entry.name : '',
    createdAt: count(entry.createdAt) || 0,
    status: typeof entry.status === 'string' ? entry.status : 'queued',
    sections: count(entry.sections),
    statements: count(entry.statements),
  }
}

// Never throws: bad JSON, an object instead of an array or junk entries all give a shorter (maybe empty) list.
function parse(raw) {
  try {
    const list = JSON.parse(raw || '[]')
    return Array.isArray(list) ? list.map(clean).filter(Boolean).slice(0, RECENT_MAX) : []
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

// For the error screen: forget the list and the old "last job" key.
export function clearSaved() {
  try {
    localStorage.removeItem(RECENT_KEY)
    localStorage.removeItem('voice2text.jobId')
  } catch {}
  window.dispatchEvent(new Event(CHANGED))
}

function subscribe(callback) {
  window.addEventListener(CHANGED, callback)
  window.addEventListener('storage', callback)
  return () => {
    window.removeEventListener(CHANGED, callback)
    window.removeEventListener('storage', callback)
  }
}

const noSubscription = () => () => {}

// null until the page has mounted in the browser (the server and the first client render both show a loading state),
// then the checked list.
export function useRecentJobs() {
  const mounted = useSyncExternalStore(noSubscription, () => true, () => false)
  const raw = useSyncExternalStore(subscribe, read, () => null)
  return useMemo(() => (mounted ? parse(raw) : null), [mounted, raw])
}
