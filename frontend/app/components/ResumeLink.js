'use client'

import Link from 'next/link'
import { useSyncExternalStore } from 'react'

const LAST_JOB_KEY = 'voice2text.jobId'
const noSubscription = () => () => {}

function readLast() {
  try {
    const id = localStorage.getItem(LAST_JOB_KEY)
    return typeof id === 'string' && id ? id : null
  } catch {
    return null
  }
}

// The last lecture of this browser, as a LINK. Nothing opens by itself: a stored id never moves or changes the page.
export default function ResumeLink({ className = '' }) {
  const id = useSyncExternalStore(noSubscription, readLast, () => null)
  if (!id) return null
  return (
    <p className={className}>
      <Link href={`/app/job/${encodeURIComponent(id)}`} className="story-link">
        Resume your last lecture
      </Link>
    </p>
  )
}
