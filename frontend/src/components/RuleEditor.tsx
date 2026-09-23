import { useState } from 'react'
import { useCatalog } from '../api/hooks'
import type { CatalogField, CatalogOperator, Condition, Rule, RuleInput, Severity } from '../api/types'
import { humanize } from '../lib/format'
import { blankRule, valueShape } from '../lib/policy'
import { Button, ErrorBanner } from './ui'

const INPUT =
  'block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-2 focus:outline-offset-0 focus:outline-slate-900'
const LABEL = 'mb-1 block text-xs font-medium text-slate-700'

/** Every input below is generated from the engine's field catalog, so a new field or operator
 *  on the backend becomes editable here with no frontend change. */
export function RuleEditor(props: {
  rule?: Rule
  programId: string | null
  onSave: (rule: RuleInput & { id?: string }) => void
  onCancel: () => void
  busy?: boolean
  error?: unknown
}) {
  const catalog = useCatalog()
  const [draft, setDraft] = useState<RuleInput & { id?: string }>(
    props.rule
      ? { ...props.rule, program_id: props.rule.program_id }
      : { ...blankRule(), program_id: props.programId },
  )

  if (!catalog.data) return null
  const fields = catalog.data.fields
  const operators = catalog.data.operators
  const field = fields.find((f) => f.key === draft.field)
  const operator = operators.find((o) => o.key === draft.operator)
  const allowed = operators.filter((o) => (field ? field.operators.includes(o.key) : false))

  const patch = (changes: Partial<RuleInput>) => setDraft({ ...draft, ...changes })

  // Changing the field can invalidate the operator and always invalidates the value.
  const pickField = (key: string) => {
    const next = fields.find((f) => f.key === key)
    const keepOperator = next && draft.operator && next.operators.includes(draft.operator)
    patch({
      field: key,
      category: next?.category ?? draft.category,
      operator: keepOperator ? draft.operator : (next?.operators[0] ?? null),
      value: null,
      label: draft.label || (next ? defaultLabel(next, keepOperator ? draft.operator : null) : ''),
    })
  }

  const valid =
    draft.label.trim().length > 0 &&
    (draft.kind === 'any_of'
      ? draft.alternatives.length > 0
      : Boolean(draft.field && draft.operator) &&
        (valueShape(operator) === 'none' || draft.value !== null))

  return (
    <div className="space-y-4 rounded-lg border border-slate-900 bg-white p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className={LABEL} htmlFor="rule-label">
            Rule name
          </label>
          <input
            id="rule-label"
            className={INPUT}
            value={draft.label}
            placeholder="Minimum FICO"
            onChange={(event) => patch({ label: event.target.value })}
          />
        </div>

        {draft.kind === 'simple' && (
          <>
            <div>
              <label className={LABEL} htmlFor="rule-field">
                Field to test
              </label>
              <select
                id="rule-field"
                className={INPUT}
                value={draft.field ?? ''}
                onChange={(event) => pickField(event.target.value)}
              >
                <option value="">Select a field…</option>
                {catalog.data.categories.map((category) => (
                  <optgroup key={category} label={humanize(category)}>
                    {fields
                      .filter((f) => f.category === category)
                      .map((f) => (
                        <option key={f.key} value={f.key}>
                          {f.label}
                          {f.derived ? ' (derived)' : ''}
                        </option>
                      ))}
                  </optgroup>
                ))}
              </select>
              {field?.description && (
                <p className="mt-1 text-xs text-slate-400">{field.description}</p>
              )}
            </div>

            <div>
              <label className={LABEL} htmlFor="rule-operator">
                Comparison
              </label>
              <select
                id="rule-operator"
                className={INPUT}
                disabled={!field}
                value={draft.operator ?? ''}
                onChange={(event) => patch({ operator: event.target.value, value: null })}
              >
                {allowed.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="sm:col-span-2">
              <ValueInput
                field={field}
                operator={operator}
                value={draft.value}
                onChange={(value) => patch({ value })}
              />
            </div>
          </>
        )}

        {draft.kind === 'any_of' && (
          <div className="sm:col-span-2">
            <span className={LABEL}>Passes when any one of these holds</span>
            <ConditionList
              conditions={draft.alternatives}
              fields={fields}
              operators={operators}
              labelled
              onChange={(alternatives) => patch({ alternatives })}
            />
          </div>
        )}

        <div>
          <label className={LABEL} htmlFor="rule-severity">
            If not met
          </label>
          <select
            id="rule-severity"
            className={INPUT}
            value={draft.severity}
            onChange={(event) => patch({ severity: event.target.value as Severity })}
          >
            <option value="hard">Decline — the lender is ineligible</option>
            <option value="soft">Preference — lowers the fit score only</option>
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="rule-category">
            Group under
          </label>
          <select
            id="rule-category"
            className={INPUT}
            value={draft.category}
            onChange={(event) => patch({ category: event.target.value })}
          >
            {catalog.data.categories.map((category) => (
              <option key={category} value={category}>
                {humanize(category)}
              </option>
            ))}
          </select>
        </div>

        <div className="sm:col-span-2">
          <span className={LABEL}>Only check this rule when… (optional)</span>
          <ConditionList
            conditions={draft.applies_when}
            fields={fields}
            operators={operators}
            onChange={(applies_when) => patch({ applies_when })}
          />
          <p className="mt-1 text-xs text-slate-400">
            With no conditions the rule always applies. Otherwise it is skipped — neither passed
            nor failed — unless every condition holds.
          </p>
        </div>

        <div className="sm:col-span-2">
          <label className={LABEL} htmlFor="rule-message">
            Custom failure message (optional)
          </label>
          <input
            id="rule-message"
            className={INPUT}
            value={draft.message_template ?? ''}
            placeholder="Lender does not operate in {actual}."
            onChange={(event) => patch({ message_template: event.target.value || null })}
          />
          <p className="mt-1 text-xs text-slate-400">
            {'Use {actual} and {expected} as placeholders. Left empty, the engine writes the message.'}
          </p>
        </div>

        <div className="sm:col-span-2 grid gap-3 sm:grid-cols-3 border-t border-slate-100 pt-3">
          <div>
            <label className={LABEL} htmlFor="rule-source-doc">
              Source Document (optional)
            </label>
            <input
              id="rule-source-doc"
              className={INPUT}
              value={draft.source_document ?? ''}
              placeholder="e.g. policy.pdf"
              onChange={(event) => patch({ source_document: event.target.value || null })}
            />
          </div>
          <div>
            <label className={LABEL} htmlFor="rule-source-page">
              Page # (optional)
            </label>
            <input
              id="rule-source-page"
              type="number"
              className={INPUT}
              value={draft.source_page ?? ''}
              placeholder="e.g. 4"
              onChange={(event) => patch({ source_page: event.target.value ? Number(event.target.value) : null })}
            />
          </div>
          <div className="sm:col-span-3">
            <label className={LABEL} htmlFor="rule-source-quote">
              PDF Source Quote (optional)
            </label>
            <input
              id="rule-source-quote"
              className={INPUT}
              value={draft.source_quote ?? ''}
              placeholder='e.g. "Minimum FICO score required is 660."'
              onChange={(event) => patch({ source_quote: event.target.value || null })}
            />
          </div>
        </div>
      </div>

      <ErrorBanner error={props.error} />

      <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-3">
        <button
          type="button"
          className="text-xs font-medium text-slate-500 underline underline-offset-4 hover:text-slate-800"
          onClick={() =>
            patch(
              draft.kind === 'simple'
                ? { kind: 'any_of', field: null, operator: null, value: null }
                : { kind: 'simple', alternatives: [] },
            )
          }
        >
          {draft.kind === 'simple' ? 'Needs alternatives instead?' : 'Back to a single check'}
        </button>
        <div className="flex gap-2">
          <Button onClick={props.onCancel}>Cancel</Button>
          <Button variant="primary" busy={props.busy} disabled={!valid} onClick={() => props.onSave(draft)}>
            {draft.id ? 'Save rule' : 'Add rule'}
          </Button>
        </div>
      </div>
    </div>
  )
}

function defaultLabel(field: CatalogField, operator: string | null): string {
  if (operator === 'gte') return `Minimum ${field.label.toLowerCase()}`
  if (operator === 'lte') return `Maximum ${field.label.toLowerCase()}`
  return field.label
}

/** The value input follows the operator's shape and the field's type. */
function ValueInput(props: {
  field: CatalogField | undefined
  operator: CatalogOperator | undefined
  value: unknown
  onChange: (value: unknown) => void
}) {
  const { field, operator } = props
  if (!field || !operator) return null
  const shape = valueShape(operator)
  if (shape === 'none') {
    return (
      <p className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-500">
        “{operator.label}” needs no comparison value.
      </p>
    )
  }

  if (shape === 'range') {
    const range = Array.isArray(props.value) ? (props.value as number[]) : [null, null]
    return (
      <div className="grid grid-cols-2 gap-3">
        {(['Minimum', 'Maximum'] as const).map((bound, index) => (
          <div key={bound}>
            <label className={LABEL} htmlFor={`rule-range-${index}`}>
              {bound}
            </label>
            <input
              id={`rule-range-${index}`}
              type="number"
              className={INPUT}
              value={range[index] ?? ''}
              onChange={(event) => {
                const next = [...range]
                next[index] = event.target.value === '' ? null : Number(event.target.value)
                props.onChange(next.every((v) => v !== null) ? next : null)
              }}
            />
          </div>
        ))}
      </div>
    )
  }

  if (shape === 'list') {
    const selected = Array.isArray(props.value) ? (props.value as string[]) : []
    return (
      <div>
        <span className={LABEL}>Values ({selected.length} selected)</span>
        <div className="flex max-h-44 flex-wrap gap-1.5 overflow-y-auto rounded-md border border-slate-200 p-2">
          {field.options.map((option) => {
            const active = selected.includes(option)
            return (
              <button
                key={option}
                type="button"
                onClick={() =>
                  props.onChange(
                    active ? selected.filter((v) => v !== option) : [...selected, option],
                  )
                }
                className={`rounded-full border px-2.5 py-1 text-xs ${
                  active
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                }`}
              >
                {humanize(option)}
              </button>
            )
          })}
        </div>
      </div>
    )
  }

  if (field.type === 'enum') {
    return (
      <div>
        <label className={LABEL} htmlFor="rule-value">
          Value
        </label>
        <select
          id="rule-value"
          className={INPUT}
          value={typeof props.value === 'string' ? props.value : ''}
          onChange={(event) => props.onChange(event.target.value || null)}
        >
          <option value="">Select…</option>
          {field.options.map((option) => (
            <option key={option} value={option}>
              {humanize(option)}
            </option>
          ))}
        </select>
      </div>
    )
  }

  if (field.type === 'boolean') {
    return (
      <div>
        <label className={LABEL} htmlFor="rule-value">
          Value
        </label>
        <select
          id="rule-value"
          className={INPUT}
          value={props.value === true ? 'true' : props.value === false ? 'false' : ''}
          onChange={(event) =>
            props.onChange(event.target.value === '' ? null : event.target.value === 'true')
          }
        >
          <option value="">Select…</option>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      </div>
    )
  }

  return (
    <div>
      <label className={LABEL} htmlFor="rule-value">
        Value{field.unit ? ` (${field.unit})` : ''}
      </label>
      <input
        id="rule-value"
        type="number"
        className={INPUT}
        value={typeof props.value === 'number' ? props.value : ''}
        onChange={(event) =>
          props.onChange(event.target.value === '' ? null : Number(event.target.value))
        }
      />
    </div>
  )
}

export function ConditionList(props: {
  conditions: Condition[]
  fields: CatalogField[]
  operators: CatalogOperator[]
  labelled?: boolean
  onChange: (conditions: Condition[]) => void
}) {
  const update = (index: number, changes: Partial<Condition>) =>
    props.onChange(props.conditions.map((c, i) => (i === index ? { ...c, ...changes } : c)))

  return (
    <div className="space-y-2">
      {props.conditions.map((condition, index) => {
        const field = props.fields.find((f) => f.key === condition.field)
        const operator = props.operators.find((o) => o.key === condition.operator)
        return (
          <div key={index} className="rounded-md border border-slate-200 p-2">
            <div className="flex flex-wrap items-end gap-2">
              <select
                aria-label="Condition field"
                className={`${INPUT} w-auto flex-1`}
                value={condition.field}
                onChange={(event) => {
                  const next = props.fields.find((f) => f.key === event.target.value)
                  update(index, {
                    field: event.target.value,
                    operator: next?.operators[0] ?? condition.operator,
                    value: null,
                  })
                }}
              >
                {props.fields.map((f) => (
                  <option key={f.key} value={f.key}>
                    {f.label}
                  </option>
                ))}
              </select>
              <select
                aria-label="Condition comparison"
                className={`${INPUT} w-auto`}
                value={condition.operator}
                onChange={(event) => update(index, { operator: event.target.value, value: null })}
              >
                {props.operators
                  .filter((o) => !field || field.operators.includes(o.key))
                  .map((o) => (
                    <option key={o.key} value={o.key}>
                      {o.label}
                    </option>
                  ))}
              </select>
              <Button
                variant="ghost"
                className="!px-2 text-red-700"
                onClick={() => props.onChange(props.conditions.filter((_, i) => i !== index))}
              >
                Remove
              </Button>
            </div>
            {valueShape(operator) !== 'none' && (
              <div className="mt-2">
                <ValueInput
                  field={field}
                  operator={operator}
                  value={condition.value}
                  onChange={(value) => update(index, { value })}
                />
              </div>
            )}
            {props.labelled && (
              <input
                className={`${INPUT} mt-2`}
                placeholder="How to describe this alternative in the reasoning"
                value={condition.label ?? ''}
                onChange={(event) => update(index, { label: event.target.value || null })}
              />
            )}
          </div>
        )
      })}
      <Button
        variant="ghost"
        className="!px-2 text-xs"
        onClick={() =>
          props.onChange([
            ...props.conditions,
            { field: props.fields[0].key, operator: props.fields[0].operators[0], value: null },
          ])
        }
      >
        + Add condition
      </Button>
    </div>
  )
}

