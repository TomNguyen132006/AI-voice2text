// job: the last answer of GET /jobs/{id}. log: when this browser saw each stage begin and end (ms),
// because the API only says which stage is current. Used by the start page and the app shell.
export function jobReducer(state, action) {
  if (action.type === 'reset') return { job: null, log: {} }
  const { job, at } = action
  const log = job.id === state.job?.id ? { ...state.log } : {}
  const before = state.job?.id === job.id ? state.job.stage : null
  if (job.stage !== before) {
    if (before && log[before] && !log[before].end) log[before] = { ...log[before], end: at }
    if (job.status === 'running' || job.status === 'queued') log[job.stage] = { start: at }
  }
  if (job.status === 'done' || job.status === 'error') {
    for (const key of Object.keys(log)) if (!log[key].end) log[key] = { ...log[key], end: at }
  }
  return { job, log }
}
