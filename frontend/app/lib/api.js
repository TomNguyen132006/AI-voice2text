// Talks to the FastAPI backend. Set NEXT_PUBLIC_API_URL in frontend/.env.local (local) or in Vercel settings (deployed).
export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

// Same list as the backend (pipeline.ALLOWED_EXTENSIONS) and the same size limit (MAX_UPLOAD_MB).
export const ALLOWED_EXTENSIONS = ['.mp3', '.m4a', '.wav', '.mp4', '.webm', '.flac', '.ogg', '.aac', '.mov', '.mkv', '.txt', '.srt', '.vtt']
export const MAX_UPLOAD_MB = 500

export function checkFile(file) {
  const dot = file.name.lastIndexOf('.')
  const ext = dot === -1 ? '' : file.name.slice(dot).toLowerCase()
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `"${ext || file.name}" is not supported. Use audio/video (${ALLOWED_EXTENSIONS.slice(0, 5).join(', ')}, ...) or a transcript (.txt, .srt, .vtt).`
  }
  if (file.size === 0) return 'The file is empty.'
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `The file is larger than ${MAX_UPLOAD_MB} MB.`
  return null
}

async function request(path, options) {
  let res
  try {
    res = await fetch(`${API_URL}${path}`, options)
  } catch {
    throw new Error(`Cannot reach the backend at ${API_URL}.`)
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {}
    const error = new Error(detail)
    error.status = res.status
    throw error
  }
  return res.json()
}

export function createJob(file) {
  const body = new FormData()
  body.append('file', file)
  return request('/jobs', { method: 'POST', body })
}

export const createSampleJob = () => request('/jobs/sample', { method: 'POST' })
export const getStats = (id) => request(`/jobs/${encodeURIComponent(id)}/stats`, { cache: 'no-store' })
export const getJob =(id) => request(`/jobs/${encodeURIComponent(id)}`, { cache: 'no-store' })

// Download links: the backend returns paths like /jobs/{id}/files/notes.md
export const fileUrl = (path) => `${API_URL}${path}`
export const zipUrl = (id) => `${API_URL}/jobs/${encodeURIComponent(id)}/files/all.zip`

export function clock(seconds) {
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}
