'use client'

const STAGE_LABELS = {
  cleaning: 'Clean transcript',
  topic_split: 'Split by topic',
  gap_finder: 'Find gaps',
  notes_writer: 'Write notes',
  judge: 'Judge',
  fixer: 'Rewrite rejected',
  slide_writer: 'Write slides',
}

const VERDICT_LABELS = {
  unsupported: 'claim not in the cited source',
  contradicts: 'contradicts the lecture',
  no_source: 'no source',
  bad_source: 'source does not exist',
  unknown_url: 'link not from our search',
  unjudged: 'judge gave no verdict',
}

const money = (n) => `$${n.toFixed(4)}`
const seconds = (ms) => `${(ms / 1000).toFixed(1)} s`

export default function StatsPanel({ stats }) {
  if (!stats || !stats.available) return null
  const { calls, judge } = stats
  const total = calls.total
  const stages = Object.entries(calls.by_stage)
  const rejected = Object.entries(judge.rejected_by_verdict || {})
  return (
    <details className="rounded-lg border border-zinc-300 p-3 text-sm dark:border-zinc-700">
      <summary className="cursor-pointer font-medium">
        How this was made: {total.calls} model calls, {Math.round(stats.total_seconds)} s, about {money(total.est_cost_usd)}
        {total.cost_is_lower_bound ? ' (at least)' : ''}
      </summary>
      <div className="mt-3 flex flex-col gap-4">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="text-zinc-500">
              <tr>
                <th className="py-1 pr-3 font-normal">Step</th>
                <th className="py-1 pr-3 font-normal">Model</th>
                <th className="py-1 pr-3 text-right font-normal">Calls</th>
                <th className="py-1 pr-3 text-right font-normal">Tokens in / out</th>
                <th className="py-1 pr-3 text-right font-normal">Model time</th>
                <th className="py-1 text-right font-normal">Cost</th>
              </tr>
            </thead>
            <tbody>
              {stages.map(([stage, row]) => (
                <tr key={stage} className="border-t border-zinc-200 dark:border-zinc-800">
                  <td className="py-1 pr-3">{STAGE_LABELS[stage] || stage}</td>
                  <td className="py-1 pr-3 font-mono text-xs">{(row.model_id || '').split('/').pop()}</td>
                  <td className="py-1 pr-3 text-right">
                    {row.calls}
                    {row.failed_calls ? ` (${row.failed_calls} failed)` : ''}
                  </td>
                  <td className="py-1 pr-3 text-right">
                    {row.prompt_tokens.toLocaleString()} / {row.completion_tokens.toLocaleString()}
                  </td>
                  <td className="py-1 pr-3 text-right">{seconds(row.latency_ms)}</td>
                  <td className="py-1 text-right">{money(row.est_cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {judge.statements !== undefined && (
          <div>
            <p className="font-medium">Judge</p>
            <p>
              {judge.passed_first_time} of {judge.statements} statements passed the first time
              {rejected.length > 0 && '. Rejected: '}
              {rejected.map(([verdict, n], i) => (
                <span key={verdict}>
                  {i > 0 && ', '}
                  {n} × {VERDICT_LABELS[verdict] || verdict}
                </span>
              ))}
              {judge.fix_attempted ? `. ${judge.fixed} of ${judge.fix_attempted} rewritten statements passed the second check.` : '.'}
            </p>
            {judge.rejections.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-zinc-600 dark:text-zinc-400">
                {judge.rejections.map((r) => (
                  <li key={r.statement_id}>
                    {r.statement_id}: {VERDICT_LABELS[r.verdict] || r.verdict}
                    {r.reason ? ` — ${r.reason}` : ''}
                  </li>
                ))}
                {judge.more_rejections > 0 && <li>…and {judge.more_rejections} more</li>}
              </ul>
            )}
          </div>
        )}
        {stats.search && stats.search.provider && (
          <p className="text-zinc-600 dark:text-zinc-400">
            Web search ({stats.search.provider}): {stats.search.provider_calls} requests, {stats.search.cache_hits} from cache
            {stats.search.errors?.length ? `, ${stats.search.errors.length} failed` : ''}.
          </p>
        )}
        {stats.warnings.map((w) => (
          <p key={w} className="text-amber-700 dark:text-amber-300">
            Note: {w}
          </p>
        ))}
      </div>
    </details>
  )
}
