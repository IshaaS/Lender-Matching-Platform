import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import {
  useCatalog,
  useCreateDraft,
  useDeleteProgram,
  useDeleteRule,
  useDiscardDraft,
  useLender,
  usePolicyVersion,
  usePublishVersion,
  useSaveProgram,
  useSaveRule,
  useVersionHistory,
} from '../api/hooks'
import type { Condition, ExtractionReview, PolicyVersion, Program, ProgramIn, Rule } from '../api/types'
import { ConditionList, RuleEditor } from '../components/RuleEditor'
import { Button, Card, ErrorBanner, Loading, PageHeader } from '../components/ui'
import { dateTime, humanize } from '../lib/format'
import { describeCondition } from '../lib/policy'
import { Pill } from './LendersList'

export function LenderPolicy() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const lender = useLender(id)
  const history = useVersionHistory(id)
  const createDraft = useCreateDraft(id)

  // Show what the URL asks for; otherwise what is live; otherwise the draft of a new lender.
  const versionId =
    params.get('v') || lender.data?.published_version?.id || lender.data?.draft_version?.id
  const version = usePolicyVersion(versionId)
  const show = (next: string) => setParams({ v: next }, { replace: true })

  if (lender.isPending) return <Loading label="Loading lender…" />
  if (lender.error) return <ErrorBanner error={lender.error} title="Could not load this lender" />

  const data = lender.data
  const draft = data.draft_version
  const viewing = version.data
  const editable = viewing?.status === 'draft'

  return (
    <>
      <PageHeader
        back={{ to: '/lenders', label: 'Lenders' }}
        title={data.name}
        subtitle={
          [data.contact_name, data.contact_email, data.contact_phone].filter(Boolean).join(' · ') ||
          'No contact details'
        }
        actions={
          !editable && (
            <Button
              variant="primary"
              busy={createDraft.isPending}
              onClick={() =>
                draft ? show(draft.id) : createDraft.mutate(undefined, { onSuccess: (v) => show(v.id) })
              }
            >
              {draft ? `Continue editing draft v${draft.version_number}` : 'Edit policy'}
            </Button>
          )
        }
      />

      <div className="space-y-5">
        <ErrorBanner error={createDraft.error} />

        {history.data && history.data.length > 1 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs font-medium text-slate-500">Versions:</span>
            {history.data.map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => show(v.id)}
                className={`rounded-full border px-3 py-1 text-xs font-medium ${
                  v.id === versionId
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                v{v.version_number} · {v.status}
              </button>
            ))}
          </div>
        )}

        {version.isPending && versionId && <Loading label="Loading policy…" />}
        <ErrorBanner error={version.error} title="Could not load this policy version" />
        {viewing && <VersionView lenderId={id} version={viewing} onLeave={show} liveId={data.published_version?.id} />}
      </div>
    </>
  )
}

function VersionView(props: {
  lenderId: string
  version: PolicyVersion
  liveId: string | undefined
  onLeave: (versionId: string) => void
}) {
  const { lenderId, version } = props
  const editable = version.status === 'draft'
  const publish = usePublishVersion(lenderId, version.id)
  const discard = useDiscardDraft(lenderId, version.id)
  const saveProgram = useSaveProgram(lenderId, version.id)
  const [addingProgram, setAddingProgram] = useState(false)

  const nextRank = Math.max(0, ...version.programs.map((p) => p.rank)) + 1

  return (
    <>
      <div
        className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 ${
          editable ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-white'
        }`}
      >
        <div className="text-sm">
          <span className="font-semibold text-slate-900">Version {version.version_number}</span>{' '}
          <Pill tone={editable ? 'amber' : version.status === 'published' ? 'emerald' : 'slate'}>
            {version.status === 'published' ? 'Live' : humanize(version.status)}
          </Pill>
          <p className="mt-1 text-xs text-slate-500">
            {editable
              ? 'Changes here affect nothing until you publish. Publishing archives the live version; past results keep pointing at the version they ran against.'
              : version.status === 'published'
                ? `Live since ${dateTime(version.published_at)}. Underwriting runs evaluate this version.`
                : 'Archived. Kept so past results stay explainable.'}
            {version.source_document && ` Source: ${version.source_document}.`}
          </p>
        </div>
        {editable && (
          <div className="flex gap-2">
            <Button
              variant="danger"
              busy={discard.isPending}
              onClick={() => {
                if (window.confirm('Discard this draft? The live policy is not affected.')) {
                  discard.mutate(undefined, { onSuccess: () => props.liveId && props.onLeave(props.liveId) })
                }
              }}
            >
              Discard draft
            </Button>
            <Button
              variant="primary"
              busy={publish.isPending}
              disabled={version.validation_errors.length > 0}
              onClick={() => publish.mutate()}
            >
              Publish v{version.version_number}
            </Button>
          </div>
        )}
      </div>

      <ErrorBanner error={publish.error ?? discard.error} />

      {version.extraction && <ExtractionChecklist review={version.extraction} editable={editable} />}

      {editable && version.validation_errors.length > 0 && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <p className="font-medium">This draft cannot be published yet</p>
          <ul className="mt-1 list-inside list-disc">
            {version.validation_errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      )}

      <RuleSection
        title="Lender-wide restrictions"
        hint="Checked before any program. Failing a hard restriction makes the lender ineligible outright."
        lenderId={lenderId}
        versionId={version.id}
        programId={null}
        rules={version.rules}
        editable={editable}
      />

      {version.programs.map((program) => (
        <ProgramCard
          key={program.id}
          lenderId={lenderId}
          versionId={version.id}
          program={program}
          editable={editable}
        />
      ))}

      {editable &&
        (addingProgram ? (
          <ProgramEditor
            initial={{ name: '', rank: nextRank, description: null, applies_when: [] }}
            busy={saveProgram.isPending}
            error={saveProgram.error}
            onCancel={() => setAddingProgram(false)}
            onSave={(program) => saveProgram.mutate(program, { onSuccess: () => setAddingProgram(false) })}
          />
        ) : (
          <Button onClick={() => setAddingProgram(true)}>+ Add program / tier</Button>
        ))}

      {version.programs.length === 0 && !editable && (
        <Card>
          <p className="text-sm text-slate-500">This version has no programs.</p>
        </Card>
      )}
    </>
  )
}

/** What the extractor was unsure about. Read this before publishing an ingested draft. */
function ExtractionChecklist({ review, editable }: { review: ExtractionReview; editable: boolean }) {
  const [open, setOpen] = useState(editable)
  const count = review.uncertainties.length
  return (
    <section className="rounded-lg border border-sky-200 bg-sky-50">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-sm">
          <span className="font-semibold text-sky-900">Extracted from {review.filename}</span>
          <span className="text-sky-800">
            {' '}by the {review.extractor ?? 'unknown'} extractor · {count} item{count === 1 ? '' : 's'} to
            review before publishing
          </span>
        </span>
        <span className="text-xs text-sky-700">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open && count > 0 && (
        <ol className="space-y-2 border-t border-sky-200 px-4 py-3">
          {review.uncertainties.map((u, index) => (
            <li key={index} className="text-sm">
              <div className="font-medium text-sky-950">{u.item}</div>
              <div className="text-sky-900">{u.reason}</div>
              {u.suggestion && <div className="text-xs text-sky-700">Suggestion: {u.suggestion}</div>}
            </li>
          ))}
        </ol>
      )}
      {open && count === 0 && (
        <p className="border-t border-sky-200 px-4 py-3 text-sm text-sky-900">
          The extractor reported nothing uncertain. Still check every threshold against the document.
        </p>
      )}
    </section>
  )
}

function ProgramCard(props: {
  lenderId: string
  versionId: string
  program: Program
  editable: boolean
}) {
  const { program, editable } = props
  const save = useSaveProgram(props.lenderId, props.versionId)
  const remove = useDeleteProgram(props.lenderId, props.versionId)
  const [editing, setEditing] = useState(false)
  const details = Object.entries(program.details)

  if (editing) {
    return (
      <ProgramEditor
        initial={{ ...program }}
        busy={save.isPending}
        error={save.error}
        onCancel={() => setEditing(false)}
        onSave={(changes) => save.mutate({ ...changes, id: program.id }, { onSuccess: () => setEditing(false) })}
      />
    )
  }

  return (
    <RuleSection
      title={`${program.rank}. ${program.name}`}
      hint={
        [
          program.description,
          program.applies_when_summary.length > 0 &&
            `Only considered when ${program.applies_when_summary.join(' and ')}.`,
        ]
          .filter(Boolean)
          .join(' ') || 'Considered for every application.'
      }
      lenderId={props.lenderId}
      versionId={props.versionId}
      programId={program.id}
      rules={program.rules}
      editable={editable}
      emptyHint="No automated criteria — every applicable application matches this program (manual underwriting)."
      headerActions={
        editable && (
          <>
            <Button variant="ghost" className="!px-2 text-xs" onClick={() => setEditing(true)}>
              Edit program
            </Button>
            <Button
              variant="ghost"
              className="!px-2 text-xs text-red-700"
              busy={remove.isPending}
              onClick={() => {
                if (window.confirm(`Delete "${program.name}" and its ${program.rules.length} rules?`)) {
                  remove.mutate(program.id)
                }
              }}
            >
              Delete
            </Button>
          </>
        )
      }
      footer={
        details.length > 0 && (
          <details className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
            <summary className="cursor-pointer font-medium text-slate-600">
              Program details (rates, documents — display only)
            </summary>
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-slate-600">
              {JSON.stringify(program.details, null, 2)}
            </pre>
          </details>
        )
      }
    />
  )
}

function ProgramEditor(props: {
  initial: ProgramIn
  busy: boolean
  error: unknown
  onSave: (program: ProgramIn) => void
  onCancel: () => void
}) {
  const catalog = useCatalog()
  const [draft, setDraft] = useState<ProgramIn>(props.initial)
  const input =
    'block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-2 focus:outline-slate-900'
  if (!catalog.data) return null

  return (
    <div className="space-y-4 rounded-lg border border-slate-900 bg-white p-4">
      <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
        <div>
          <label htmlFor="program-name" className="mb-1 block text-xs font-medium text-slate-700">
            Program / tier name
          </label>
          <input
            id="program-name"
            className={input}
            value={draft.name}
            placeholder="Tier 1"
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="program-rank" className="mb-1 block text-xs font-medium text-slate-700">
            Rank (1 = best)
          </label>
          <input
            id="program-rank"
            type="number"
            min={1}
            className={input}
            value={draft.rank}
            onChange={(event) => setDraft({ ...draft, rank: Math.max(1, Number(event.target.value)) })}
          />
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="program-description" className="mb-1 block text-xs font-medium text-slate-700">
            Description (optional)
          </label>
          <input
            id="program-description"
            className={input}
            value={draft.description ?? ''}
            onChange={(event) => setDraft({ ...draft, description: event.target.value || null })}
          />
        </div>
        <div className="sm:col-span-2">
          <span className="mb-1 block text-xs font-medium text-slate-700">
            Only consider this program when… (optional)
          </span>
          <ConditionList
            conditions={draft.applies_when ?? []}
            fields={catalog.data.fields}
            operators={catalog.data.operators}
            onChange={(applies_when: Condition[]) => setDraft({ ...draft, applies_when })}
          />
          <p className="mt-1 text-xs text-slate-400">
            Programs are tried best rank first; the applicant gets the first applicable program
            whose hard rules all pass.
          </p>
        </div>
      </div>
      <ErrorBanner error={props.error} />
      <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
        <Button onClick={props.onCancel}>Cancel</Button>
        <Button
          variant="primary"
          busy={props.busy}
          disabled={!draft.name.trim()}
          onClick={() => props.onSave(draft)}
        >
          Save program
        </Button>
      </div>
    </div>
  )
}

function RuleSection(props: {
  title: string
  hint: string
  lenderId: string
  versionId: string
  programId: string | null
  rules: Rule[]
  editable: boolean
  emptyHint?: string
  headerActions?: React.ReactNode
  footer?: React.ReactNode
}) {
  const catalog = useCatalog()
  const save = useSaveRule(props.lenderId, props.versionId)
  const remove = useDeleteRule(props.lenderId, props.versionId)
  // 'new' = adding; a rule id = editing that rule; null = read mode.
  const [open, setOpen] = useState<string | null>(null)

  const categories = [...new Set(props.rules.map((r) => r.category))]

  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-slate-900">{props.title}</h2>
          <p className="mt-0.5 text-xs text-slate-500">{props.hint}</p>
        </div>
        <div className="flex shrink-0 gap-1">{props.headerActions}</div>
      </header>

      {props.rules.length === 0 && open !== 'new' && (
        <p className="px-5 py-4 text-sm text-slate-400">{props.emptyHint ?? 'No rules yet.'}</p>
      )}

      {categories.map((category) => (
        <div key={category}>
          <h3 className="bg-slate-50 px-5 py-1.5 text-xs font-medium tracking-wide text-slate-500 uppercase">
            {humanize(category)}
          </h3>
          <ul className="divide-y divide-slate-50">
            {props.rules
              .filter((rule) => rule.category === category)
              .map((rule) =>
                open === rule.id ? (
                  <li key={rule.id} className="p-3">
                    <RuleEditor
                      rule={rule}
                      programId={props.programId}
                      busy={save.isPending}
                      error={save.error}
                      onCancel={() => setOpen(null)}
                      onSave={(changes) => save.mutate(changes, { onSuccess: () => setOpen(null) })}
                    />
                  </li>
                ) : (
                  <li key={rule.id} className="flex items-start gap-3 px-5 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <span className="text-sm font-medium text-slate-900">{rule.label}</span>
                        {rule.severity === 'soft' && <Pill tone="slate">Preference</Pill>}
                        {rule.kind === 'any_of' && <Pill tone="slate">Any of</Pill>}
                      </div>
                      <p className="mt-0.5 text-sm text-slate-600">{rule.summary}</p>
                      {rule.applies_when.length > 0 && catalog.data && (
                        <p className="mt-0.5 text-xs text-slate-400">
                          Only when{' '}
                          {rule.applies_when
                            .map((c) => describeCondition(c, catalog.data.fields, catalog.data.operators))
                            .join(' and ')}
                        </p>
                      )}
                      {(rule.source_document || rule.source_quote) && (
                        <p className="mt-1 text-xs text-slate-500 italic bg-slate-50 rounded px-2 py-1 border border-slate-100">
                          Source: {rule.source_document || 'Policy PDF'}
                          {rule.source_page != null ? ` (p. ${rule.source_page})` : ''}
                          {rule.source_quote ? `: "${rule.source_quote}"` : ''}
                        </p>
                      )}
                    </div>
                    {props.editable && (
                      <div className="flex shrink-0 gap-1">
                        <Button variant="ghost" className="!px-2 text-xs" onClick={() => setOpen(rule.id)}>
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          className="!px-2 text-xs text-red-700"
                          onClick={() => {
                            if (window.confirm(`Delete the rule "${rule.label}"?`)) remove.mutate(rule.id)
                          }}
                        >
                          Delete
                        </Button>
                      </div>
                    )}
                  </li>
                ),
              )}
          </ul>
        </div>
      ))}

      {props.editable && (
        <div className="border-t border-slate-100 p-3">
          {open === 'new' ? (
            <RuleEditor
              programId={props.programId}
              busy={save.isPending}
              error={save.error}
              onCancel={() => setOpen(null)}
              onSave={(rule) => save.mutate(rule, { onSuccess: () => setOpen(null) })}
            />
          ) : (
            <Button variant="ghost" className="text-xs" onClick={() => setOpen('new')}>
              + Add rule
            </Button>
          )}
          <ErrorBanner error={remove.error} />
        </div>
      )}
      {props.footer}
    </section>
  )
}
