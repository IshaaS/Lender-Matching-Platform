import type { CatalogField, CatalogOperator, Condition, RuleInput } from '../api/types'
import { formatFeature } from './format'

export const valueShape = (operator: CatalogOperator | undefined) => operator?.value_shape ?? 'none'

export const blankRule = (): RuleInput => ({
  kind: 'simple',
  label: '',
  category: 'credit',
  severity: 'hard',
  field: null,
  operator: null,
  value: null,
  alternatives: [],
  applies_when: [],
  message_template: null,
})

/** "Time in business at least 3 yrs" - the same phrasing the API uses for rule summaries. */
export function describeCondition(
  condition: Condition,
  fields: CatalogField[],
  operators: CatalogOperator[],
): string {
  const field = fields.find((f) => f.key === condition.field)
  const operator = operators.find((o) => o.key === condition.operator)
  if (!field || !operator) return `${condition.field} ${condition.operator}`
  if (operator.value_shape === 'none') return `${field.label} ${operator.label}`
  const value = condition.value
  const text = Array.isArray(value)
    ? value
        .map((v) => formatFeature(field, v as string | number))
        .join(operator.value_shape === 'range' ? ' – ' : ', ')
    : formatFeature(field, (value ?? null) as string | number | boolean | null)
  return `${field.label} ${operator.label} ${text}`
}
