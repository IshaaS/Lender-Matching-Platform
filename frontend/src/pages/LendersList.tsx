import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCreateLender, useLenders } from '../api/hooks'
import { OnboardFromPdf } from '../components/OnboardFromPdf'
import { Button, EmptyState, ErrorBanner, Loading, PageHeader } from '../components/ui'
import { dateTime } from '../lib/format'

export function LendersList() {
  const lenders = useLenders()
  const create = useCreateLender()
  const navigate = useNavigate()
  const [adding, setAdding] = useState(false)
  const [onboarding, setOnboarding] = useState(false)
  const [name, setName] = useState('')

  const submit = () =>
    create.mutate(
      { name: name.trim() },
      { onSuccess: (lender) => navigate(`/lenders/${lender.id}?v=${lender.draft_version?.id ?? ''}`) },
    )

  return (
    <>
      <PageHeader
        title="Lenders"
        subtitle="Credit policies as data: programs, rules and restrictions for each lender."
        back={{ to: '/', label: 'Home' }}
        actions={
          <>
            {!onboarding && (
              <Button variant="primary" onClick={() => { setOnboarding(true); setAdding(false) }}>
                Onboard from PDF
              </Button>
            )}
            {!adding && (
              <Button onClick={() => { setAdding(true); setOnboarding(false) }}>
                Add lender manually
              </Button>
            )}
          </>
        }
      />

      {onboarding && (
        <div className="mb-5">
          <OnboardFromPdf onClose={() => setOnboarding(false)} />
        </div>
      )}

      {adding && (
        <div className="mb-5 rounded-lg border border-slate-900 bg-white p-4">
          <label htmlFor="lender-name" className="mb-1 block text-xs font-medium text-slate-700">
            Lender name
          </label>
          <div className="flex flex-wrap gap-2">
            <input
              id="lender-name"
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && name.trim() && submit()}
              placeholder="e.g. Summit Equipment Finance"
              className="min-w-64 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-2 focus:outline-slate-900"
            />
            <Button onClick={() => setAdding(false)}>Cancel</Button>
            <Button variant="primary" busy={create.isPending} disabled={!name.trim()} onClick={submit}>
              Create with empty draft policy
            </Button>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            The lender starts with a draft policy. Add programs and rules, test with an application,
            then publish — nothing is evaluated until a version is published.
          </p>
          <div className="mt-2">
            <ErrorBanner error={create.error} />
          </div>
        </div>
      )}

      {lenders.isPending && <Loading label="Loading lenders…" />}
      <ErrorBanner error={lenders.error} title="Could not load lenders" />
      {lenders.data?.length === 0 && (
        <EmptyState title="No lenders yet" hint="Add a lender to start modelling its credit policy." />
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {lenders.data?.map((lender) => (
          <button
            key={lender.id}
            type="button"
            onClick={() => navigate(`/lenders/${lender.id}`)}
            className="rounded-lg border border-slate-200 bg-white p-5 text-left transition-colors hover:border-slate-400"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-base font-semibold text-slate-900">{lender.name}</h2>
              <div className="flex shrink-0 gap-1.5">
                {!lender.is_active && <Pill tone="slate">Inactive</Pill>}
                {lender.published_version ? (
                  <Pill tone="emerald">Live v{lender.published_version.version_number}</Pill>
                ) : (
                  <Pill tone="slate">Not published</Pill>
                )}
                {lender.draft_version && <Pill tone="amber">Draft v{lender.draft_version.version_number}</Pill>}
              </div>
            </div>
            <p className="mt-2 text-sm text-slate-600">
              {lender.program_count} program{lender.program_count === 1 ? '' : 's'} · {lender.rule_count}{' '}
              rule{lender.rule_count === 1 ? '' : 's'}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              {lender.published_version?.source_document ?? 'No source document'} · updated{' '}
              {dateTime(lender.updated_at)}
            </p>
          </button>
        ))}
      </div>
    </>
  )
}

export function Pill({ tone, children }: { tone: 'emerald' | 'amber' | 'slate' | 'red'; children: React.ReactNode }) {
  const tones = {
    emerald: 'bg-emerald-100 text-emerald-800',
    amber: 'bg-amber-100 text-amber-800',
    slate: 'bg-slate-100 text-slate-600',
    red: 'bg-red-100 text-red-800',
  }
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>
  )
}
