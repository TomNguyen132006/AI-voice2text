'use client'

import Link from 'next/link'
import { parentRoute } from '../lib/routes'

// "Back" to the fixed parent page of the current one (see parentRoute). It REPLACES the current history entry, so the page
// you leave is not kept: pressing it can never build a loop of pages that point at each other.
export default function BackLink({ pathname, className = '' }) {
  const parent = parentRoute(pathname)
  if (!parent) return null
  return (
    <Link href={parent.href} replace aria-label={`Back to ${parent.label}`} className={`shell-back ${className}`}>
      <svg aria-hidden viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M15 5l-7 7 7 7" />
      </svg>
      {parent.label}
    </Link>
  )
}
