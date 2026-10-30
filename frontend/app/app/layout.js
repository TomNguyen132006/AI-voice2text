import { Suspense } from 'react'
import '../shell.css'
import AppShell from '../components/AppShell'

export const metadata = {
  title: 'Lecturesque app: your lectures and notes',
  description: 'Your recent lectures, a new upload, and pre-generated examples.',
}

// usePathname() in the shell needs a Suspense boundary because /app/job/[id] has no fixed id at build time.
export default function AppLayout({ children }) {
  return (
    <Suspense fallback={null}>
      <AppShell>{children}</AppShell>
    </Suspense>
  )
}
