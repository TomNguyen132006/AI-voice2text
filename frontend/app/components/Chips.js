'use client'

import { useState } from 'react'
import { clock, domainOf, safeHttpUrl } from '../lib/api'

const chip = 'inline-flex min-h-8 items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium'

function ClockIcon() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.5V8l2.2 1.4" />
    </svg>
  )
}

function LinkIcon() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6.5 3.5H4A1.5 1.5 0 0 0 2.5 5v7A1.5 1.5 0 0 0 4 13.5h7a1.5 1.5 0 0 0 1.5-1.5V9.5M9 2.5h4.5V7M13.5 2.5L7.5 8.5" />
    </svg>
  )
}

// A moment in the lecture. Click to see the whole time range and the transcript segment it comes from.
export function LectureChip({ source }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={`Lecture at ${clock(source.start)}, show details`}
        className={`${chip} bg-accent-soft text-accent-ink hover:bg-accent/15`}
      >
        <ClockIcon />
        {clock(source.start)}
      </button>
      {open && (
        <span className="text-sm text-muted">
          Said between {clock(source.start)} and {clock(source.end)} ({source.segment_id})
        </span>
      )}
    </span>
  )
}

// A web page: shows the site name and opens the page in a new tab. Only http(s) addresses become links.
export function WebChip({ source }) {
  const href = safeHttpUrl(source.url)
  const domain = domainOf(source.url)
  const label = source.title ? `${domain}: ${source.title}` : domain
  if (!href) {
    return <span className={`${chip} border border-line-strong text-muted`}>{domain}</span>
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={source.title || domain}
      aria-label={`${label} (opens in a new tab)`}
      className={`${chip} max-w-full border border-line-strong bg-surface text-ink hover:border-accent hover:text-accent-ink`}
    >
      <LinkIcon />
      <span className="truncate">{domain}</span>
    </a>
  )
}

const BADGES = {
  verified: ['Verified', 'Checked by the judge against its sources.'],
  rewritten: ['Rewritten', 'It failed the first check, was rewritten from its own sources, and passed the second check.'],
  unjudged: ['Not judged', 'The judge gave no verdict for this note.'],
}

// The judge's verdict for one note (shown only when the stats say so).
export function JudgeBadge({ kind }) {
  const [text, explain] = BADGES[kind]
  return (
    <span title={explain} className="inline-flex items-center gap-1 text-sm text-muted">
      <span aria-hidden className={kind === 'verified' ? 'text-accent' : ''}>
        {kind === 'verified' ? '✓' : kind === 'rewritten' ? '↻' : '○'}
      </span>
      {text}
      <span className="sr-only">. {explain}</span>
    </span>
  )
}
