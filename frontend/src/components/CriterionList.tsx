import { useCatalog } from '../api/hooks'
import type { CatalogField, Criterion } from '../api/types'
import { formatFeature, humanize } from '../lib/format'

const CATEGORY_ORDER = [
  'geography',
  'industry',
  'business',
  'credit',
  'history',
  'guarantor',
  'loan',
  'equipment',
  'other',
]

const OUTCOME = {
  passed: { mark: '✓', chip: 'bg-emerald-100 text-emerald-700', text: 'text-slate-700' },
  failed: { mark: '✕', chip: 'bg-red-100 text-red-700', text: 'text-red-900' },
  missing: { mark: '?', chip: 'bg-amber-100 text-amber-700', text: 'text-amber-900' },
  skipped: { mark: '–', chip: 'bg-slate-100 text-slate-400', text: 'text-slate-400' },
} as const

/** Renders a comparison value in the unit the engine's catalog declares for that field,
 *  so "15000" reads as "$15,000" and a range as "$10,000 – $75,000". */
function describe(value: unknown, field: CatalogField | undefined): string {
  if (value == null) return 'not provided'
  if (typeof value === 'boolean' || typeof value === 'number' || typeof value === 'string') {
    return formatFeature(field, value)
  }
  if (Array.isArray(value)) {
    const parts = value.map((entry) =>
      entry && typeof entry === 'object' && 'label' in entry
        ? String((entry as { label: unknown }).label)
        : describe(entry, field),
    )
    // A two-number array is a between-range; anything else is a list of accepted values.
    return value.length === 2 && value.every((v) => typeof v === 'number')
      ? parts.join(' – ')
      : parts.join(', ')
  }
  return Object.entries(value as Record<string, unknown>)
    .map(([key, entry]) => `${humanize(key)}: ${describe(entry, field)}`)
    .join(' · ')
}

function Row({ criterion, field }: { criterion: Criterion; field: CatalogField | undefined }) {
  const style = OUTCOME[criterion.outcome]
  const comparable = criterion.outcome !== 'skipped' && criterion.field_key !== null
  // Operators like "is yes" carry no comparison value; the message already states the rule.
  const hasExpected = criterion.expected !== null && criterion.expected !== undefined
  return (
    <li className="flex gap-3 px-4 py-3">
      <span
        aria-label={criterion.outcome}
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${style.chip}`}
      >
        {style.mark}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className={`text-sm font-medium ${style.text}`}>{criterion.label}</span>
          {criterion.severity === 'soft' && (
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-slate-500 uppercase">
              Preference
            </span>
          )}
        </div>
        <p className={`mt-0.5 text-sm ${criterion.outcome === 'failed' ? 'text-red-700' : 'text-slate-500'}`}>
          {criterion.message}
        </p>
        {comparable && (
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
            {hasExpected && (
              <span>
                Required:{' '}
                <span className="font-medium text-slate-700">{describe(criterion.expected, field)}</span>
              </span>
            )}
            <span>
              Applicant:{' '}
              <span className={`font-medium ${criterion.outcome === 'failed' ? 'text-red-700' : 'text-slate-700'}`}>
                {describe(criterion.actual, field)}
              </span>
            </span>
          </div>
        )}
      </div>
    </li>
  )
}

export function CriterionList({ criteria, emptyHint }: { criteria: Criterion[]; emptyHint: string }) {
  const catalog = useCatalog()
  const fields = new Map(catalog.data?.fields.map((field) => [field.key, field]))

  if (criteria.length === 0) {
    return <p className="px-4 py-6 text-center text-sm text-slate-400">{emptyHint}</p>
  }

  const categories = [...new Set(criteria.map((c) => c.category))].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b),
  )

  return (
    <div className="divide-y divide-slate-100">
      {categories.map((category) => {
        const group = criteria.filter((c) => c.category === category)
        const failed = group.filter((c) => c.outcome === 'failed').length
        return (
          <section key={category}>
            <h4 className="flex items-center justify-between bg-slate-50 px-4 py-1.5 text-xs font-medium tracking-wide text-slate-500 uppercase">
              {humanize(category)}
              {failed > 0 && <span className="text-red-600">{failed} not met</span>}
            </h4>
            <ul className="divide-y divide-slate-50">
              {group.map((criterion) => (
                <Row
                  key={criterion.id}
                  criterion={criterion}
                  field={criterion.field_key ? fields.get(criterion.field_key) : undefined}
                />
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
