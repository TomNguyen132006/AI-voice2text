// The static parts of the start page: nav, values strip, "how it works", footer. No state, no data from the API.
import Link from 'next/link'
import HealthStatus from './HealthStatus'
import ThemeToggle from './ThemeToggle'

function Tick() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8.5l3.2 3L13 4.5" />
    </svg>
  )
}

export function Nav() {
  return (
    <header className="story-nav story-wrap">
      <Link href="/" className="story-logo" aria-label="Lecturesque home">
        <span aria-hidden="true" />
        Lecturesque
      </Link>
      <nav aria-label="Main navigation">
        <Link href="/#how" className="nav-link nav-how">
          How it works
        </Link>
        <Link href="/app/library" className="nav-link">
          Library
        </Link>
        <ThemeToggle />
      </nav>
    </header>
  )
}

export function Values() {
  return (
    <div className="story-values story-wrap" aria-label="What you get">
      <span>
        <Tick /> Every statement has a source
      </span>
      <span>
        <Tick /> Notes, slides and .pptx
      </span>
      <span>
        <Tick /> Built on NVIDIA Nemotron + Nebius
      </span>
    </div>
  )
}

const STEPS = [
  {
    label: 'THE TRANSCRIPT',
    title: 'Upload',
    copy: 'Drop a transcript (.txt, .srt or .vtt). Audio works only on a server that has a GPU.',
  },
  {
    label: 'THE CHECK',
    title: 'Check',
    copy: 'Watch the stages run with live progress: cleaning, web search, notes, the judge, slides.',
  },
  {
    label: 'THE FILES',
    title: 'Download',
    copy: 'Take the transcript (.txt), the notes (.md) and the slides (.pptx), or all of them in one .zip.',
  },
]

export function HowItWorks() {
  return (
    <section id="how" className="story-how" aria-labelledby="how-title">
      <div className="story-wrap">
        <div className="how-heading">
          <p className="handwritten">three steps</p>
          <h2 id="how-title">From a lecture to notes with receipts.</h2>
          <p>Every note links to the moment in the lecture or the web page it came from.</p>
        </div>
        <div className="how-grid">
          {STEPS.map((step, i) => (
            <article className="how-card" key={step.title}>
              <span className="step-number" aria-hidden="true">
                {i + 1}
              </span>
              <span className="story-label">{step.label}</span>
              <h3>
                <span className="sr-only">Step {i + 1}: </span>
                {step.title}
              </h3>
              <p>{step.copy}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

export function Footer() {
  return (
    <footer className="story-footer story-wrap">
      <Link href="/" className="story-logo">
        <span aria-hidden="true" />
        Lecturesque
      </Link>
      <p>Built with Nemotron on Nebius Token Factory</p>
      <HealthStatus />
    </footer>
  )
}
