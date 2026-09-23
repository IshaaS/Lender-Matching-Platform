import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  keys,
  useApplication,
  useCatalog,
  useResult,
  useRun,
  useRuns,
  useStartRun,
} from '../api/hooks'
import type { MatchResultSummary, ProgramSummary, Run } from '../api/types'
import { CriterionList } from '../components/CriterionList'
import {
  Button,
  Card,
  ErrorBanner,
  Loading,
  PageHeader,
  Spinner,
  StatusBadge,
} from '../components/ui'
import { dateTime, formatFeature, humanize, money } from '../lib/format'
import { defaultProgram, programTone } from '../lib/results'

export function RunResults() {
  const { id = '', runId = '' } = useParams()
  const navigate = useNavigate()
  const client = useQueryClient()
  const application = useApplication(id)
  const run = useRun(runId)
  const runs = useRuns(id)
  const startRun = useStartRun(id)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const results = run.data?.results ?? []
  // Falling back to the top-ranked result also survives a re-run, which mints new result ids.
  const selected = results.find((r) => r.id === selectedId) ?? results[0]

  if (run.isPending) return <Loading label="Loading results…" />
  if (run.error) return <ErrorBanner error={run.error} title="Could not load this run" />

  const data = run.data
  const eligible = results.filter((r) => r.decision === 'eligible' || (!r.decision && r.eligible))
  const manualReview = results.filter((r) => r.decision === 'manual_review')
  const needsInfo = results.filter((r) => r.decision === 'needs_information')
  const business = application.data?.business.legal_name ?? 'Application'

  return (
    <>
      <PageHeader
        back={{ to: `/applications/${id}`, label: business }}
        title="Underwriting results"
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={data.status} />
            <span>
              {dateTime(data.created_at)} · {data.mode === 'hatchet' ? 'Hatchet workflow' : 'in-process'}
              {application.data?.loan.amount != null && ` · ${money(application.data.loan.amount)}`}
            </span>
          </span>
        }
        actions={
          <>
            {runs.data && runs.data.length > 1 && (
              <select
                value={runId}
                onChange={(event) => navigate(`/applications/${id}/runs/${event.target.value}`)}
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
              >
                {runs.data.map((option, index) => (
                  <option key={option.id} value={option.id}>
                    {index === 0 ? 'Latest run' : `Run ${runs.data.length - index}`} ·{' '}
                    {dateTime(option.created_at)}
                  </option>
                ))}
              </select>
            )}
            <Button
              variant="primary"
              busy={startRun.isPending || application.data?.status === 'underwriting'}
              onClick={() =>
                startRun.mutate(undefined, {
                  onSuccess: (fresh) => {
                    void client.invalidateQueries({ queryKey: keys.runs(id) })
                    navigate(`/applications/${id}/runs/${fresh.id}`)
                  },
                })
              }
            >
              Re-run underwriting
            </Button>
          </>
        }
      />

      <div className="space-y-5">
        <ErrorBanner error={startRun.error} />

        {data.status === 'failed' && (
          <ErrorBanner error={new Error(data.error ?? 'Unknown error')} title="This underwriting run failed" />
        )}

        {(data.status === 'queued' || data.status === 'running') && (
          <Card>
            <div className="flex items-center gap-3 text-sm text-slate-600">
              <Spinner /> Evaluating {results.length || ''} lender policies… this page updates automatically.
            </div>
          </Card>
        )}

        {data.status === 'completed' && (
          <>
            <Summary run={data} />
            <div className="grid gap-5 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
              <LenderRail results={results} selectedId={selected?.id} onSelect={setSelectedId} />
              {selected && <LenderDetail key={selected.id} result={selected} />}
            </div>
            {eligible.length === 0 && manualReview.length === 0 && needsInfo.length === 0 && (
              <Card>
                <p className="text-sm text-slate-600">
                  No lender matched. Open each lender above to see exactly which criteria failed, or{' '}
                  <button
                    type="button"
                    className="font-medium text-slate-900 underline underline-offset-4"
                    onClick={() => navigate(`/applications/${id}`)}
                  >
                    duplicate the application
                  </button>{' '}
                  to try different terms.
                </p>
              </Card>
            )}
            <FeatureSnapshot run={data} />
          </>
        )}
      </div>
    </>
  )
}

function Summary({ run }: { run: Run }) {
  const eligible = run.results.filter((r) => r.decision === 'eligible' || (!r.decision && r.eligible))
  const manualReview = run.results.filter((r) => r.decision === 'manual_review')
  const needsInfo = run.results.filter((r) => r.decision === 'needs_information')
  const best = run.results.find((r) => r.decision === 'eligible' || r.decision === 'manual_review' || r.eligible)
  const errored = run.results.filter((r) => r.status === 'error')
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-x-10 gap-y-4">
        <Stat label="Lenders evaluated" value={String(run.results.length)} />
        <Stat
          label="Eligible"
          value={`${eligible.length}`}
          tone={eligible.length > 0 ? 'good' : 'bad'}
        />
        {manualReview.length > 0 && (
          <Stat label="Manual review" value={String(manualReview.length)} tone="good" hint="Human underwriting required" />
        )}
        {needsInfo.length > 0 && (
          <Stat label="Needs info" value={String(needsInfo.length)} hint="Missing required applicant fields" />
        )}
        {best && <Stat label="Best match" value={best.lender_name} hint={best.matched_program_name} />}
        {best && best.fit_score != null && <Stat label="Fit score" value={String(best.fit_score)} tone="good" />}
        {errored.length > 0 && <Stat label="Evaluation errors" value={String(errored.length)} tone="bad" />}
      </div>
    </Card>
  )
}

function Stat(props: { label: string; value: string; hint?: string | null; tone?: 'good' | 'bad' }) {
  const tone =
    props.tone === 'good' ? 'text-emerald-700' : props.tone === 'bad' ? 'text-red-700' : 'text-slate-900'
  return (
    <div>
      <div className="text-xs text-slate-500">{props.label}</div>
      <div className={`mt-0.5 text-lg font-semibold ${tone}`}>{props.value}</div>
      {props.hint && <div className="text-xs text-slate-500">{props.hint}</div>}
    </div>
  )
}

function LenderRail(props: {
  results: MatchResultSummary[]
  selectedId: string | undefined
  onSelect: (id: string) => void
}) {
  return (
    <div className="space-y-2 lg:sticky lg:top-4 lg:self-start">
      {props.results.map((result) => {
        const active = result.id === props.selectedId
        const isManual = result.decision === 'manual_review'
        const isNeedsInfo = result.decision === 'needs_information'
        const isEligible = result.decision === 'eligible' || (result.eligible && !result.decision)

        return (
          <button
            key={result.id}
            type="button"
            onClick={() => props.onSelect(result.id)}
            className={`flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors ${
              active ? 'border-slate-900 bg-white shadow-xs' : 'border-slate-200 bg-white hover:border-slate-300'
            }`}
          >
            <span className="mt-0.5 w-4 text-xs tabular-nums text-slate-400">{result.rank}</span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-slate-900">{result.lender_name}</div>
              <div className={`mt-0.5 text-xs ${isEligible ? 'text-slate-500' : isManual ? 'text-amber-800 font-medium' : isNeedsInfo ? 'text-blue-800 font-medium' : 'text-red-700'}`}>
                {result.status === 'error'
                  ? 'Could not be evaluated'
                  : isManual
                    ? `Manual review required (${result.matched_program_name})`
                    : isNeedsInfo
                      ? `Information needed (${result.matched_program_name})`
                      : isEligible
                        ? result.matched_program_name
                        : `${result.rejection_reasons.length} reason${result.rejection_reasons.length === 1 ? '' : 's'} not to lend`}
              </div>
              {!isEligible && !isManual && !isNeedsInfo && result.status !== 'error' && (
                <div className="mt-2 flex items-center gap-2">
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-amber-400"
                      style={{ width: `${Math.round(result.near_miss_ratio * 100)}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-slate-400">
                    {Math.round(result.near_miss_ratio * 100)}% met
                  </span>
                </div>
              )}
            </div>
            {isEligible && (
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold tabular-nums text-emerald-800">
                {result.fit_score}
              </span>
            )}
            {isManual && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                Manual Review
              </span>
            )}
            {isNeedsInfo && (
              <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-800">
                Needs Info
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

function LenderDetail({ result }: { result: MatchResultSummary }) {
  const detail = useResult(result.id)
  const [programName, setProgramName] = useState<string | null>(defaultProgram(result))

  const criteria = detail.data?.criteria ?? []
  const restrictions = criteria.filter((c) => c.program_name === null)
  const programCriteria = criteria.filter((c) => c.program_name === programName)
  const program = result.program_summaries.find((p) => p.name === programName)
  const breakdown = result.score_breakdown

  const isManual = result.decision === 'manual_review'
  const isNeedsInfo = result.decision === 'needs_information'
  const isEligible = result.decision === 'eligible' || (result.eligible && !result.decision)

  return (
    <div className="space-y-5">
      <Card
        title={result.lender_name}
        hint={`Policy version ${result.policy_version_number}`}
        actions={
          isManual ? (
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
              Manual Review Required
            </span>
          ) : isNeedsInfo ? (
            <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-800">
              Needs Information
            </span>
          ) : isEligible ? (
            <div className="text-right">
              <div className="text-2xl font-semibold text-emerald-700 tabular-nums">{result.fit_score}</div>
              <div className="text-xs text-slate-500">fit score</div>
            </div>
          ) : (
            <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-medium text-red-800">
              Not eligible
            </span>
          )
        }
      >
        {result.status === 'error' ? (
          <ErrorBanner error={new Error(result.error ?? 'Unknown error')} title="This lender's policy could not be evaluated" />
        ) : result.eligible ? (
          <>
            <p className="text-sm text-slate-700">
              Matched <span className="font-semibold text-slate-900">{result.matched_program_name}</span>
              {breakdown.total != null && (
                <span className="text-slate-500">
                  {' '}— tier {breakdown.tier}, headroom {breakdown.headroom}, preferences {breakdown.soft}
                </span>
              )}
            </p>
            {breakdown.notes && (
              <ul className="mt-2 space-y-0.5 text-xs text-slate-500">
                {breakdown.notes.map((note) => (
                  <li key={note}>· {note}</li>
                ))}
              </ul>
            )}
            <ProgramDetails details={result.program_details} />
          </>
        ) : (
          <>
            <p className="text-sm font-medium text-slate-900">Why this lender declined</p>
            <ul className="mt-2 space-y-1.5">
              {result.rejection_reasons.map((reason, index) => (
                <li key={index} className="flex gap-2 text-sm text-red-800">
                  <span aria-hidden>✕</span>
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      {result.status !== 'error' && (
        <Card
          title="Criteria"
          hint="Every check this lender applies, with what was required and what the applicant showed."
        >
          <div className="-mx-5 -mb-5">
            {restrictions.length > 0 && (
              <div className="border-b border-slate-200">
                <h3 className="px-4 pt-1 pb-2 text-xs font-semibold text-slate-700">
                  Lender-wide restrictions
                </h3>
                <CriterionList criteria={restrictions} emptyHint="No lender-wide restrictions." />
              </div>
            )}
            <div>
              <div className="flex flex-wrap items-center gap-1.5 px-4 pt-3 pb-2">
                <span className="mr-1 text-xs font-semibold text-slate-700">Programs:</span>
                {result.program_summaries.map((summary) => (
                  <ProgramChip
                    key={summary.name}
                    summary={summary}
                    active={summary.name === programName}
                    matched={summary.name === result.matched_program_name}
                    onClick={() => setProgramName(summary.name)}
                  />
                ))}
              </div>
              {program && !program.applicable && (
                <p className="mx-4 mb-2 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-500">
                  {program.applicability_note ?? 'This program does not apply to this application.'}
                </p>
              )}
              {detail.isPending ? (
                <Loading label="Loading criteria…" />
              ) : (
                <CriterionList
                  criteria={programCriteria}
                  emptyHint={
                    program?.applicable === false
                      ? 'Not evaluated — the program does not apply.'
                      : 'This program publishes no automated criteria (manual underwriting).'
                  }
                />
              )}
            </div>
          </div>
          <ErrorBanner error={detail.error} />
        </Card>
      )}
    </div>
  )
}

function ProgramChip(props: {
  summary: ProgramSummary
  active: boolean
  matched: boolean
  onClick: () => void
}) {
  const { summary, active, matched } = props
  const tone = programTone(summary, matched)
  return (
    <button
      type="button"
      onClick={props.onClick}
      className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${tone} ${
        active ? 'ring-2 ring-slate-900 ring-offset-1' : 'hover:bg-slate-50'
      }`}
    >
      {summary.name}
      {matched && ' ✓'}
      {summary.applicable && !matched && summary.hard_failures > 0 && ` · ${summary.hard_failures}`}
      {!summary.applicable && ' · n/a'}
    </button>
  )
}

function ProgramDetails({ details }: { details: Record<string, unknown> }) {
  const entries = Object.entries(details).filter(([, value]) => value != null)
  if (entries.length === 0) return null
  return (
    <dl className="mt-4 grid gap-x-6 gap-y-2 border-t border-slate-100 pt-4 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt className="text-xs text-slate-500">{humanize(key)}</dt>
          <dd className="text-sm text-slate-800">
            {typeof value === 'object' ? (
              <ul className="space-y-0.5">
                {(Array.isArray(value) ? value : Object.entries(value as Record<string, unknown>)).map(
                  (entry, index) => (
                    <li key={index}>
                      {Array.isArray(entry) ? `${entry[0]}: ${String(entry[1])}` : String(entry)}
                    </li>
                  ),
                )}
              </ul>
            ) : (
              String(value)
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function FeatureSnapshot({ run }: { run: Run }) {
  const catalog = useCatalog()
  const [open, setOpen] = useState(false)
  if (!run.feature_snapshot || !catalog.data) return null
  const fields = catalog.data.fields.filter((field) => run.feature_snapshot?.[field.key] != null)
  return (
    <Card
      title="What the engine evaluated"
      hint="The exact feature set this run used, derived from the application at run time."
      actions={
        <Button variant="ghost" onClick={() => setOpen(!open)}>
          {open ? 'Hide' : 'Show'} {fields.length} values
        </Button>
      }
    >
      {open && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
          {fields.map((field) => (
            <div key={field.key}>
              <dt className="text-xs text-slate-500">{field.label}</dt>
              <dd className="text-sm font-medium text-slate-900">
                {formatFeature(field, run.feature_snapshot?.[field.key] ?? null)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  )
}
