'use client'

import { STAGES, duration } from '../lib/api'

const STEP_LABELS = {
  cleaning: 'Clean transcript',
  topic_split: 'Split by topic',
  gap_finder: 'Find gaps',
  notes_writer: 'Write notes',
  judge: 'Judge',
  fixer: 'Rewrite rejected notes',
  slide_writer: 'Write slides',
}

const VERDICT_LABELS = {
  unsupported: 'a claim is not in the cited source',
  contradicts: 'contradicts the lecture',
  no_source: 'no source',
  bad_source: 'the source does not exist',
  unknown_url: 'the link is not from our search',
  unjudged: 'the judge gave no verdict',
}

const money = (n) => `$${n.toFixed(4)}`
const seconds = (ms) => `${(ms / 1000).toFixed(1)} s`
const number = (n) => n.toLocaleString('en-US')

// "nvidia/Nemotron-3-Ultra-550b-a55b" -> "Nemotron Ultra"
function modelName(id = '') {
  const lower = id.toLowerCase()
  for (const size of ['nano', 'super', 'ultra']) {
    if (lower.includes(size)) return `Nemotron ${size[0].toUpperCase()}${size.slice(1)}`
  }
  return id.split('/').pop() || 'Unknown model'
}

const clip = (text, max = 90) => (text.length > max ? `${text.slice(0, max - 1)}…` : text)

// stats: undefined while loading, null or {available: false} when this job has none.
export default function StatsPanel({ stats, statements = [] }) {
  if (stats === undefined) {
    return (
      <p role="status" className="min-h-14 rounded-3xl border border-border bg-card px-5 py-4 text-muted-foreground">
        Loading how this was made…
      </p>
    )
  }
  if (!stats || !stats.available) return null
  const { calls, judge } = stats
  const total = calls.total
  const steps = Object.entries(calls.by_stage)
  const modelsUsed = [...new Set(steps.map(([, row]) => modelName(row.model_id)))]
  const rejected = Object.entries(judge?.rejected_by_verdict || {})
  const textOf = Object.fromEntries(statements.map((s) => [s.id, s.text]))
  const perStage = STAGES.filter(([key]) => stats.seconds_per_stage?.[key] !== undefined)

  return (
    <section aria-labelledby="stats-heading" className="md:relative md:left-1/2 md:w-[min(960px,calc(100vw-3rem))] md:-translate-x-1/2">
      <details className="rounded-3xl border border-border bg-card">
        <summary id="stats-heading" className="cursor-pointer px-5 py-4 font-semibold text-foreground">
          How this was made: {total.calls} model calls, {duration(stats.total_seconds)}, about {money(total.est_cost_usd)}
          {total.cost_is_lower_bound ? ' (at least)' : ''}
        </summary>
        <div className="flex flex-col gap-6 border-t border-border px-5 py-5">
          <p>
            <span className="story-label text-muted-foreground">MODELS USED </span>
            {modelsUsed.join(', ')}. Speech to text (NVIDIA Parakeet) is used only when an audio file is uploaded to a server with a GPU.
          </p>
          <div>
            <h3 className="mb-2 font-serif text-2xl">Models and cost by step</h3>
            <div role="region" aria-label="Model usage by step" tabIndex={0} className="overflow-x-auto">
              <table className="w-full min-w-[34rem] text-left">
                <thead className="text-muted-foreground">
                  <tr>
                    <th scope="col" className="py-1 pr-3 font-medium">Step</th>
                    <th scope="col" className="py-1 pr-3 font-medium">Model</th>
                    <th scope="col" className="py-1 pr-3 text-right font-medium">Calls</th>
                    <th scope="col" className="py-1 pr-3 text-right font-medium">Tokens in / out</th>
                    <th scope="col" className="py-1 pr-3 text-right font-medium">Model time</th>
                    <th scope="col" className="py-1 text-right font-medium">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {steps.map(([step, row]) => (
                    <tr key={step} className="border-t border-border">
                      <th scope="row" className="py-1.5 pr-3 font-normal">{STEP_LABELS[step] || step}</th>
                      <td className="py-1.5 pr-3">{modelName(row.model_id)}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {row.calls}
                        {row.failed_calls ? ` (${row.failed_calls} failed)` : ''}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {number(row.prompt_tokens)} / {number(row.completion_tokens)}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{seconds(row.latency_ms)}</td>
                      <td className="py-1.5 text-right tabular-nums">{money(row.est_cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-border font-medium">
                    <th scope="row" className="py-1.5 pr-3 text-left">Total</th>
                    <td className="py-1.5 pr-3" />
                    <td className="py-1.5 pr-3 text-right tabular-nums">{total.calls}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">
                      {number(total.prompt_tokens)} / {number(total.completion_tokens)}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">{seconds(total.latency_ms)}</td>
                    <td className="py-1.5 text-right tabular-nums">{money(total.est_cost_usd)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <p className="mt-2 text-muted-foreground">Speech to text (Parakeet) is not in these numbers.</p>
          </div>

          {perStage.length > 0 && (
            <div>
              <h3 className="mb-2 font-serif text-2xl">Time by stage</h3>
              <ul className="flex flex-wrap gap-x-5 gap-y-1 text-muted-foreground">
                {perStage.map(([key, title]) => (
                  <li key={key}>
                    {title}: <span className="tabular-nums text-foreground">{duration(stats.seconds_per_stage[key])}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {judge && judge.statements !== undefined && (
            <div>
              <h3 className="mb-2 font-serif text-2xl">Judge</h3>
              <p>
                {judge.passed_first_time} of {judge.statements} notes passed the first check
                {rejected.length > 0 && '. Rejected: '}
                {rejected.map(([verdict, n], i) => (
                  <span key={verdict}>
                    {i > 0 && ', '}
                    {n} × {VERDICT_LABELS[verdict] || verdict}
                  </span>
                ))}
                {judge.fix_attempted ? `. ${judge.fixed} of ${judge.fix_attempted} rewritten notes passed the second check.` : '.'}
              </p>
              {judge.rejections.length > 0 && (
                <ul className="mt-2 flex flex-col gap-2 text-muted-foreground">
                  {judge.rejections.map((r) => (
                    <li key={r.statement_id}>
                      {textOf[r.statement_id] ? 'First check failed for the note that now reads ' : 'First check failed for note '}
                      <span className="text-foreground">“{clip(textOf[r.statement_id] || r.statement_id)}”</span>
                      <br />
                      The judge said {VERDICT_LABELS[r.verdict] || r.verdict}
                      {r.reason ? `: ${r.reason}` : ''}
                    </li>
                  ))}
                  {judge.more_rejections > 0 && <li>…and {judge.more_rejections} more</li>}
                </ul>
              )}
            </div>
          )}

          {stats.search && stats.search.provider && (
            <p className="text-muted-foreground">
              Web search ({stats.search.provider}): {stats.search.provider_calls} requests, {stats.search.cache_hits} from cache
              {stats.search.errors?.length ? `, ${stats.search.errors.length} failed` : ''}.
            </p>
          )}
          {(stats.warnings || []).map((warning) => (
            <p key={warning} className="text-muted-foreground">
              Note: {warning}
            </p>
          ))}
        </div>
      </details>
    </section>
  )
}
