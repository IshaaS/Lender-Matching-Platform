import { describe, expect, it } from 'vitest'
import type { CatalogField } from '../api/types'
import { applicationSchema, emptyApplication } from './applicationForm'
import { formatFeature, humanize, money, yesNo } from './format'

const field = (over: Partial<CatalogField>): CatalogField => ({
  key: 'x', label: 'X', type: 'number', category: 'credit', unit: '', options: [],
  derived: false, description: '', operators: [], ...over,
})

describe('humanize', () => {
  it('turns catalog tokens into prose but leaves state codes alone', () => {
    expect(humanize('class_8_truck')).toBe('Class 8 truck')
    expect(humanize('sale_leaseback')).toBe('Sale leaseback')
    expect(humanize('llc')).toBe('LLC')
    expect(humanize('TX')).toBe('TX')
    expect(humanize(null)).toBe('—')
  })
})

describe('formatFeature', () => {
  it('formats by the unit declared in the engine catalog', () => {
    expect(formatFeature(field({ unit: 'money' }), 120000)).toBe('$120,000')
    expect(formatFeature(field({ unit: 'percent' }), 42.5)).toBe('42.5%')
    expect(formatFeature(field({ unit: 'years' }), 1)).toBe('1 yr')
    expect(formatFeature(field({ unit: 'years' }), 2.5)).toBe('2.5 yrs')
    expect(formatFeature(field({ unit: 'score' }), 725)).toBe('725')
  })

  it('renders missing values and booleans the way lender rules read them', () => {
    expect(formatFeature(field({}), null)).toBe('—')
    expect(formatFeature(field({ type: 'boolean' }), true)).toBe('Yes')
    expect(formatFeature(field({ type: 'boolean' }), false)).toBe('No')
    expect(yesNo(null)).toBe('—')
    expect(money(null)).toBe('—')
  })
})

describe('applicationSchema', () => {
  it('accepts an entirely empty draft', () => {
    expect(applicationSchema.safeParse(emptyApplication()).success).toBe(true)
  })

  it('rejects values outside the ranges the API enforces', () => {
    const payload = emptyApplication()
    payload.guarantors[0].fico_score = 900
    const result = applicationSchema.safeParse(payload)
    expect(result.success).toBe(false)
    expect(result.error?.issues[0].path).toEqual(['guarantors', 0, 'fico_score'])
  })

  it('keeps unanswered optional fields null rather than coercing them', () => {
    const parsed = applicationSchema.parse(emptyApplication())
    expect(parsed.business.years_in_business).toBeNull()
    expect(parsed.loan.corp_only).toBe(false)
  })
})
