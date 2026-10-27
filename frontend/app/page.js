import HealthStatus from './components/HealthStatus'
import LectureApp from './components/LectureApp'

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-8 p-6">
      <header className="flex flex-col gap-2 pt-6">
        <h1 className="text-3xl font-semibold">AI-voice2text</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Turn a lecture recording into study notes, slides and a transcript, where every point has a source: 📍 a moment
          in the lecture or 🌐 a web link.
        </p>
      </header>
      <LectureApp />
      <HealthStatus />
    </main>
  )
}
