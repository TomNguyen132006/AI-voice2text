'use client'

import { useEffect, useState } from 'react'

// Set in frontend/.env.local (local) or in Vercel project settings (deployed).
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export default function HealthStatus() {
  const [state, setState] = useState({ loading: true, data: null, error: null })

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((err) => setState({ loading: false, data: null, error: err.message }))
  }, [])

  return (
    <div className="rounded-lg border border-zinc-300 p-4 dark:border-zinc-700">
      <p className="text-sm text-zinc-500">
        Backend: <code>{API_URL}</code>
      </p>
      {state.loading && <p>Checking backend…</p>}
      {state.data && (
        <p className="text-green-600">
          Backend says: <code>{JSON.stringify(state.data)}</code>
        </p>
      )}
      {state.error && <p className="text-red-600">Cannot reach backend: {state.error}</p>}
    </div>
  )
}
