import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  keys,
  useApplication,
  useCatalog,
  useDeleteApplication,
  useDuplicateApplication,
  useFeatures,
  useRuns,
  useStartRun,
  useSubmitApplication,
} from '../api/hooks'
import type { Application, Run } from '../api/types'
import {
  Button,
  Card,
  DataList,
  ErrorBanner,
  LinkButton,
  Loading,
  PageHeader,
  StatusBadge,
} from '../components/ui'
import { dateTime, formatFeature, humanize, money, yesNo } from '../lib/format'

export function ApplicationDetail() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const client = useQueryClient()
  const application = useApplication(id)
  const submit = useSubmitApplication(id)
  const duplicate = useDuplicateApplication(id)
  const remove = useDeleteApplication(id)
  const startRun = useStartRun(id)

  if (application.isPending) return <Loading label="Loading application…" />
  if (application.error) return <ErrorBanner error={application.error} title="Could not load this application" />

  const app = application.data
  const isDraft = app.status === 'draft'
  const running = app.status === 'underwriting'
  const refresh = () => client.invalidateQueries({ queryKey: keys.application(id) })

  return (
    <>
      <PageHeader
        back={{ to: '/applications', label: 'Applications' }}
        title={app.business.legal_name ?? 'Untitled draft'}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={app.status} />
            <span>
              {money(app.loan.amount)} · {app.loan.term_months ?? '—'} months ·{' '}
              {humanize(app.business.industry)} · {app.business.state ?? '—'}
            </span>
          </span>
        }
        actions={
          <>
            {isDraft && <LinkButton to={`/applications/${id}/edit`}>Edit</LinkButton>}
            <Button
              busy={duplicate.isPending}
              onClick={() => duplicate.mutate(undefined, { onSuccess: (copy) => navigate(`/applications/${copy.id}/edit`) })}
            >
              Duplicate
            </Button>
            {isDraft && (
              <Button
                variant="danger"
                busy={remove.isPending}
                onClick={() => {
                  if (window.confirm('Delete this draft? This cannot be undone.')) {
                    remove.mutate(undefined, { onSuccess: () => navigate('/applications') })
                  }
                }}
              >
                Delete
              </Button>
            )}
            {isDraft ? (
              <Button
                variant="primary"
                busy={submit.isPending}
                disabled={app.missing_fields.length > 0}
                onClick={() => submit.mutate(undefined, { onSuccess: refresh })}
              >
                Submit
              </Button>
            ) : (
              <Button
                variant="primary"
                busy={startRun.isPending || running}
                onClick={() =>
                  startRun.mutate(undefined, {
                    onSuccess: () => {
                      void refresh()
                      void client.invalidateQueries({ queryKey: keys.runs(id) })
                    },
                  })
                }
              >
                {running ? 'Underwriting…' : app.latest_run ? 'Re-run underwriting' : 'Run underwriting'}
              </Button>
            )}
          </>
        }
      />

      <div className="space-y-5">
        <ErrorBanner error={submit.error ?? startRun.error ?? duplicate.error ?? remove.error} />

        {isDraft && app.missing_fields.length > 0 && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <p className="font-medium">
              {app.missing_fields.length} field{app.missing_fields.length === 1 ? '' : 's'} still needed before this can be submitted
            </p>
            <p className="mt-1 text-amber-800">{app.missing_fields.map((m) => m.label).join(' · ')}</p>
          </div>
        )}

        {!isDraft && <Underwriting application={app} />}

        <Card title="Business">
          <DataList
            items={[
              ['Legal name', app.business.legal_name],
              ['Entity type', humanize(app.business.entity_type)],
              ['Industry', humanize(app.business.industry)],
              ['State', app.business.state],
              ['Time in business', app.business.years_in_business != null ? `${app.business.years_in_business} yrs` : null],
              ['Annual revenue', money(app.business.annual_revenue)],
              ['Physical location', yesNo(app.business.has_physical_location)],
              ['US-based', yesNo(app.business.is_us_based)],
              ...(app.business.trucks_operated != null ? [['Trucks operated', app.business.trucks_operated] as [string, number]] : []),
            ]}
          />
        </Card>

        <Card title="Loan request & equipment">
          <DataList
            items={[
              ['Amount', money(app.loan.amount)],
              ['Term', app.loan.term_months != null ? `${app.loan.term_months} months` : null],
              ['Transaction', humanize(app.loan.transaction_type)],
              ['Down payment', app.loan.down_payment_pct != null ? `${app.loan.down_payment_pct}%` : null],
              ['Soft costs', app.loan.soft_cost_pct != null ? `${app.loan.soft_cost_pct}%` : null],
              ['Guarantee', app.loan.corp_only ? 'Corp only' : 'Personal guarantee'],
            ]}
          />
          {app.equipment.map((item, index) => (
            <div key={index} className="mt-4 border-t border-slate-100 pt-4">
              <DataList
                items={[
                  ['Equipment', humanize(item.category)],
                  ['Description', item.description],
                  ['Model year', item.model_year],
                  ['Condition', humanize(item.condition)],
                  ['Mileage', item.mileage != null ? `${item.mileage.toLocaleString()} mi` : null],
                  ['Titled', yesNo(item.is_titled)],
                ]}
              />
            </div>
          ))}
        </Card>

        {!app.loan.corp_only &&
          app.guarantors.map((g, index) => {
            const history = [
              g.has_bankruptcy && `Bankruptcy${g.bankruptcy_discharge_date ? ` (discharged ${g.bankruptcy_discharge_date})` : ' (not discharged)'}`,
              g.has_judgments && 'Judgments',
              g.has_foreclosures && 'Foreclosures',
              g.has_repossessions && 'Repossessions',
              g.has_tax_liens && 'Tax liens',
              g.has_recent_collections && 'Recent collections',
            ].filter(Boolean)
            return (
              <Card key={index} title={`Guarantor${app.guarantors.length > 1 ? ` ${index + 1}` : ''}: ${g.full_name ?? 'Unnamed'}`}>
                <DataList
                  items={[
                    ['Ownership', g.ownership_pct != null ? `${g.ownership_pct}%` : null],
                    ['FICO score', g.fico_score],
                    ['Homeowner', yesNo(g.is_homeowner)],
                    ['US citizen', yesNo(g.is_us_citizen)],
                    ['Industry experience', g.industry_experience_years != null ? `${g.industry_experience_years} yrs` : null],
                    ['Revolving balance / limit', `${money(g.revolving_balance)} / ${money(g.revolving_credit_limit)}`],
                    ['Unsecured debt', money(g.unsecured_debt)],
                    ...(g.has_cdl != null ? [['CDL', g.has_cdl ? `Class ${g.cdl_class ?? '?'} · ${g.cdl_years ?? '?'} yrs` : 'No'] as [string, string]] : []),
                    ...(g.is_licensed_medical_professional ? [['Licensed', `${g.years_licensed ?? '?'} yrs`] as [string, string]] : []),
                    ['Credit history', history.length ? <span key="history" className="text-red-700">{history.join(', ')}</span> : 'Clean'],
                  ]}
                />
              </Card>
            )
          })}

        <Card title="Business credit">
          <DataList
            items={[
              ['PayNet MasterScore', app.business_credit.paynet_score ?? 'No score'],
              ['Largest comparable credit', money(app.business_credit.largest_comparable_credit)],
              ['Comparable contracts', app.business_credit.comparable_contracts_count],
              ['Trade lines', app.business_credit.trade_lines_count],
              ['Trade history', app.business_credit.trade_history_years != null ? `${app.business_credit.trade_history_years} yrs` : null],
              ['Clean payment history', app.business_credit.clean_payment_history_months != null ? `${app.business_credit.clean_payment_history_months} mo` : null],
            ]}
          />
        </Card>

        <DerivedFeatures id={id} />
      </div>
    </>
  )
}

function Underwriting({ application }: { application: Application }) {
  const latest = application.latest_run
  const runs = useRuns(application.id)
  const client = useQueryClient()
  const completedRunId = latest?.status === 'completed' ? latest.id : null
  useEffect(() => {
    if (completedRunId) void client.invalidateQueries({ queryKey: keys.runs(application.id) })
  }, [completedRunId, application.id, client])
  // The runs list carries lender results; refetched whenever the latest run changes state.
  const detail = runs.data?.find((run) => run.id === latest?.id)

  if (!latest) {
    return (
      <Card title="Underwriting">
        <p className="text-sm text-slate-500">
          Not underwritten yet. Run underwriting to evaluate this application against every lender with a published policy.
        </p>
      </Card>
    )
  }
  return (
    <Card
      title="Underwriting"
      hint={`Latest run ${dateTime(latest.created_at)} · ${latest.mode === 'hatchet' ? 'Hatchet workflow' : 'in-process'}`}
      actions={<StatusBadge status={latest.status} />}
    >
      {latest.status === 'failed' && <ErrorBanner error={new Error(latest.error ?? 'Unknown error')} title="The underwriting run failed" />}
      {(latest.status === 'queued' || latest.status === 'running') && (
        <p className="text-sm text-slate-500">Evaluating lender policies… this page updates automatically.</p>
      )}
      {latest.status === 'completed' && (
        <>
          <p className="text-sm text-slate-700">
            <span className="font-semibold text-slate-900">
              {latest.eligible_count} of {latest.lender_count}
            </span>{' '}
            lenders eligible
            {latest.best_lender && (
              <>
                {' '}· best match <span className="font-semibold text-slate-900">{latest.best_lender}</span> ({latest.best_program}, fit {latest.best_score})
              </>
            )}
          </p>
          {detail ? <RankedResults run={detail} /> : runs.isFetching && <Loading label="Loading results…" />}
          <div className="mt-4">
            <Link to={`/applications/${application.id}/runs/${latest.id}`} className="text-sm font-medium text-slate-900 underline underline-offset-4">
              View full results and reasoning →
            </Link>
          </div>
        </>
      )}
      {runs.data && runs.data.length > 1 && (
        <p className="mt-3 text-xs text-slate-400">{runs.data.length} runs in total for this application.</p>
      )}
    </Card>
  )
}

function RankedResults({ run }: { run: Run }) {
  return (
    <ul className="mt-4 divide-y divide-slate-100 rounded-md border border-slate-200">
      {run.results.map((result) => (
        <li key={result.id} className="flex items-start gap-3 px-4 py-2.5 text-sm">
          <span className="w-5 pt-0.5 text-xs tabular-nums text-slate-400">{result.rank}</span>
          <div className="min-w-0 flex-1">
            <div className="font-medium text-slate-900">{result.lender_name}</div>
            <div className={`truncate text-xs ${result.eligible ? 'text-slate-500' : 'text-red-700'}`}>
              {result.eligible ? result.matched_program_name : (result.rejection_reasons[0] ?? 'Not eligible')}
            </div>
          </div>
          {result.eligible ? (
            <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold tabular-nums text-emerald-800">
              Fit {result.fit_score}
            </span>
          ) : (
            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">Not eligible</span>
          )}
        </li>
      ))}
    </ul>
  )
}

function DerivedFeatures({ id }: { id: string }) {
  const features = useFeatures(id)
  const catalog = useCatalog()
  if (!features.data || !catalog.data) return null
  const derived = catalog.data.fields.filter((field) => field.derived)
  return (
    <Card title="Derived features" hint="Computed from the application; these are what lender rules are evaluated against.">
      <DataList items={derived.map((field) => [field.label, formatFeature(field, features.data[field.key] ?? null)])} />
    </Card>
  )
}
