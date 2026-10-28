import HealthStatus from './components/HealthStatus'
import LectureApp from './components/LectureApp'

export default function Home() {
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to the content
      </a>
      <div className="mx-auto flex w-full max-w-[760px] flex-1 flex-col px-4 sm:px-6">
        <header className="pt-10 pb-8 sm:pt-14">
          <h1 className="font-read text-3xl font-semibold tracking-tight sm:text-4xl">AI-voice2text</h1>
          <p className="mt-3 text-lg text-muted">
            Upload a lecture transcript and get study notes, slides and a timestamped transcript. Every point shows its source.
          </p>
        </header>
        <main id="main" className="flex-1 pb-14">
          <LectureApp />
        </main>
        <footer className="flex flex-col gap-2 border-t border-line py-6 text-sm text-muted">
          <p>Built with Nemotron on Nebius Token Factory</p>
          <HealthStatus />
        </footer>
      </div>
    </>
  )
}
