import { redirect } from 'next/navigation'

// /app opens the library.
export default function AppHome() {
  redirect('/app/library')
}
