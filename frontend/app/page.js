import HealthStatus from './components/HealthStatus'

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 p-6">
      <h1 className="text-3xl font-semibold">AI-voice2text</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        Turn a lecture recording into study notes, slides and a transcript, where every
        point has a source.
      </p>
      <HealthStatus />
    </main>
  )
}
