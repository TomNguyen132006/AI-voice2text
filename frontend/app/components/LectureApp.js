import Link from 'next/link'
import { HowItWorks, Values } from './Landing'
import ResumeLink from './ResumeLink'

function Arrow() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  )
}

// The start page. Nothing is uploaded here: the upload lives at /app/new (reached from the Library), a job at /app/job/[id].
export default function LectureApp() {
  return (
    <main id="story-main" tabIndex={-1}>
      <section className="story-hero story-wrap" aria-labelledby="hero-title">
        <div className="story-hero-copy">
          <p className="handwritten">notes with receipts ✦</p>
          <h1 id="hero-title">
            Your lecture, turned into notes <span className="marker">you can check.</span>
          </h1>
          <p className="story-lede">Upload a lecture transcript. You get notes, slides and sources, with every line tied to a timestamp or a link.</p>
          <p className="hero-note">
            <strong>Source-checked</strong> means the cited source supports the statement. It does not check that the source itself is true.
          </p>
          <ResumeLink />
        </div>
        <div className="story-hero-art">
          <span className="story-sticker hero-sticker" aria-hidden="true">
            source-checked
          </span>
          <div className="story-panel !py-6">
            <section aria-labelledby="start-heading" className="flex flex-col gap-4">
              <div>
                <p className="story-label text-muted-foreground">START HERE</p>
                <h2 id="start-heading" className="sr-only">
                  Start
                </h2>
              </div>
              <Link href="/app/library" className="story-button story-button-coral w-full !min-h-[60px] text-lg">
                Start your own lecture
                <Arrow />
              </Link>
              <p className="text-[15px] text-muted-foreground">Transcripts (.txt, .srt, .vtt). Audio needs a local GPU.</p>
            </section>
          </div>
        </div>
      </section>
      <Values />
      <HowItWorks />
    </main>
  )
}
