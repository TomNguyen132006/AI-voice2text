'use client'

import { useRouter } from 'next/navigation'
import { clearSaved } from '../lib/recent'

// The safety net of the app: if a page of /app crashes, this shows instead of a blank page. The shell around it stays.
export default function AppError({ reset }) {
  const router = useRouter()

  function backToLibrary() {
    reset()
    router.replace('/app/library')
  }

  function clearAndReload() {
    clearSaved()
    reset()
    router.replace('/app/library')
  }

  return (
    <section role="alert" className="flex flex-col gap-5">
      <div>
        <p className="handwritten">oh no ✦</p>
        <h2 className="text-4xl leading-tight">Something went wrong</h2>
      </div>
      <p className="text-muted-foreground">
        This page could not be shown. Your lectures on the server are not affected. If it keeps happening, clear the saved list in this browser and try again.
      </p>
      <div className="flex flex-col gap-3 sm:flex-row">
        <button type="button" onClick={backToLibrary} className="story-button story-button-coral story-button-small">
          Back to Library
        </button>
        <button type="button" onClick={clearAndReload} className="story-button story-button-outline story-button-small">
          Clear saved list
        </button>
      </div>
    </section>
  )
}
