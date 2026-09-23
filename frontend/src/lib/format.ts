import type { CatalogField, FeatureValue } from '../api/types'

const UPPER = new Set(['llc', 'us', 'atm', 'cdl'])

/** "class_8_truck" -> "Class 8 truck" */
export function humanize(token: string | null | undefined): string {
  if (!token) return '—'
  if (/^[A-Z]{2}$/.test(token)) return token
  const words = token.split('_').map((w) => (UPPER.has(w) ? w.toUpperCase() : w))
  const text = words.join(' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export const money = (value: number | null | undefined): string =>
  value == null ? '—' : `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`

const number = (value: number): string =>
  value.toLocaleString('en-US', { maximumFractionDigits: 1 })

export const yesNo = (value: boolean | null | undefined): string =>
  value == null ? '—' : value ? 'Yes' : 'No'

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

/** Formats a feature value using the unit declared in the engine's field catalog. */
export function formatFeature(field: CatalogField | undefined, value: FeatureValue): string {
  if (value == null) return '—'
  if (typeof value === 'boolean') return yesNo(value)
  if (typeof value === 'string') return humanize(value)
  switch (field?.unit) {
    case 'money':
      return money(value)
    case 'percent':
      return `${number(value)}%`
    case 'years':
      return `${number(value)} yr${value === 1 ? '' : 's'}`
    case 'months':
      return `${number(value)} mo`
    case 'miles':
      return `${number(value)} mi`
    default:
      return number(value)
  }
}
