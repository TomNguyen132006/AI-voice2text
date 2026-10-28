// Talks to the FastAPI backend. Set NEXT_PUBLIC_API_URL in frontend/.env.local (local) or in Vercel settings (deployed).
export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

// Same list as the backend (pipeline.ALLOWED_EXTENSIONS) and the same size limit (MAX_UPLOAD_MB).
export const ALLOWED_EXTENSIONS = ['.mp3', '.m4a', '.wav', '.mp4', '.webm', '.flac', '.ogg', '.aac', '.mov', '.mkv', '.txt', '.srt', '.vtt']
export const MAX_UPLOAD_MB = 10
// The server's default for MAX_TRANSCRIPT_CHARS (about 20 minutes of speech). The server answers 413 with its real limit when it is over.
export const MAX_TRANSCRIPT_CHARS = 15000

export function checkFile(file) {
  const dot = file.name.lastIndexOf('.')
  const ext = dot === -1 ? '' : file.name.slice(dot).toLowerCase()
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `We can't use "${ext || file.name}" files. Upload a transcript: .txt, .srt or .vtt.`
  }
  if (file.size === 0) return 'That file is empty.'
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `That file is larger than ${MAX_UPLOAD_MB} MB.`
  return null
}

async function request(path, options) {
  let res
  try {
    res = await fetch(`${API_URL}${path}`, options)
  } catch {
    const error = new Error('network')
    error.kind = 'network'
    throw error
  }
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {}
    const error = new Error(`HTTP ${res.status}`)
    error.status = res.status
    error.detail = detail
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
export const getJob = (id) => request(`/jobs/${encodeURIComponent(id)}`, { cache: 'no-store' })

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

// "4 min 8 s" for a duration in seconds.
export function duration(seconds) {
  const total = Math.round(seconds)
  if (total < 60) return `${total} s`
  const m = Math.floor(total / 60)
  const s = total % 60
  return s ? `${m} min ${s} s` : `${m} min`
}

// Only http(s) links are ever put in an href (a "javascript:" url must never become a link).
export function safeHttpUrl(url) {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null
  } catch {
    return null
  }
}

export function domainOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

// The six stages the API reports (Job.stage), with a short title and what happens inside.
export const STAGES = [
  ['transcribing', 'Reading the file', 'Loading the transcript'],
  ['cleaning', 'Cleaning and topic split', 'Fixing the transcript, then splitting it by topic'],
  ['enriching', 'Gap finder and web search', 'Finding terms a beginner needs, then searching the web for them'],
  ['writing', 'Notes', 'Writing the notes, each with its sources'],
  ['judging', 'Judge and fix', 'Checking every note against its sources and rewriting the ones that fail'],
  ['exporting', 'Slides and files', 'Writing the slides and the files to download'],
]
const STAGE_TITLES = Object.fromEntries(STAGES.map(([key, title]) => [key, title]))

// A server message is shown only when it is short plain text (never JSON or a stack trace).
function plainText(text, max = 300) {
  const clean = (text || '').replace(/\s+/g, ' ').trim()
  if (!clean || clean.length > max || /^[{[]/.test(clean) || /traceback|\bat .+:\d+/i.test(clean)) return ''
  return clean
}

// Turns a failed request into words for a person: { title, message }.
export function describeError(error) {
  const status = error?.status
  const detail = plainText(error?.detail, 200)
  if (error?.kind === 'network' || status === undefined) {
    return {
      title: "Can't reach the server",
      message: 'It may be starting up (the free plan can take about 30 seconds) or you may be offline. Try again in a moment.',
    }
  }
  if (status === 400) {
    if (/transcribe audio|no gpu/i.test(error.detail || '')) {
      return {
        title: "This server can't transcribe audio",
        message: 'Audio needs a server with a GPU, and this one has none. Upload a transcript instead: a .txt, .srt or .vtt file.',
      }
    }
    return { title: "We can't use that file", message: detail || 'Check that it is a .txt, .srt or .vtt transcript and that it is not empty.' }
  }
  if (status === 404) {
    return { title: 'This job was not found', message: 'The server may have restarted and lost it. Upload the file again.' }
  }
  if (status === 409) return { title: 'Not ready yet', message: 'The job is still running. Wait a moment and try again.' }
  if (status === 413) return { title: 'That file is too large', message: detail || `Files can be up to ${MAX_UPLOAD_MB} MB.` }
  if (status === 429) {
    return { title: 'The server is busy', message: detail || 'Too many requests, or the daily limit was reached. Wait a few minutes and try again.' }
  }
  if (status >= 500) return { title: 'The server had a problem', message: 'Try again in a minute. If it keeps happening, upload a smaller file.' }
  return { title: 'Something went wrong', message: 'Please try again.' }
}

// A job that ended with status "error": its error text is "<stage>: <message>".
export function describeJobFailure(job) {
  const raw = job.error || ''
  const match = raw.match(/^([a-z_]+):\s*([\s\S]*)$/)
  const stage = match ? match[1] : job.stage
  return {
    title: `Stopped at: ${STAGE_TITLES[stage] || stage || 'an unknown step'}`,
    message: 'Something went wrong while processing this lecture. Your file was not changed. Try again, or try a different file.',
    detail: plainText(match ? match[2] : raw),
  }
}
