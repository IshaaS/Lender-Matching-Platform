import { describe, expect, it } from 'vitest'
import type { MatchResultSummary, ProgramSummary } from '../api/types'
import { defaultProgram } from './results'

const program = (over: Partial<ProgramSummary>): ProgramSummary => ({
  name: 'Tier 1', rank: 1, applicable: true, applicability_note: null, eligible: false,
  hard_failures: 0, ...over,
})

const result = (over: Partial<MatchResultSummary>): MatchResultSummary => ({
  id: 'r1', rank: 1, lender_id: 'l1', lender_name: 'Test', policy_version_id: 'v1',
  policy_version_number: 1, status: 'evaluated', error: null, eligible: false,
  matched_program_name: null, fit_score: 0, score_breakdown: {}, near_miss_ratio: 0,
  rejection_reasons: [], decision: 'ineligible', program_details: {}, program_summaries: [], ...over,
})

describe('defaultProgram', () => {
  it('shows the matched program when the lender is eligible', () => {
    const match = result({
      eligible: true,
      matched_program_name: 'Tier 2',
      program_summaries: [program({}), program({ name: 'Tier 2', rank: 2, eligible: true })],
    })
    expect(defaultProgram(match)).toBe('Tier 2')
  })

  it('shows the program with the fewest unmet criteria when nothing matched', () => {
    const near = result({
      program_summaries: [
        program({ name: 'Tier 1', rank: 1, hard_failures: 3 }),
        program({ name: 'Tier 3', rank: 3, hard_failures: 1 }),
        program({ name: 'Tier 2', rank: 2, hard_failures: 2 }),
      ],
    })
    expect(defaultProgram(near)).toBe('Tier 3')
  })

  it('breaks ties toward the least demanding tier, as the rejection reasons do', () => {
    const tied = result({
      program_summaries: [
        program({ name: 'Tier 1', rank: 1, hard_failures: 1 }),
        program({ name: 'Tier 3', rank: 3, hard_failures: 1 }),
      ],
    })
    expect(defaultProgram(tied)).toBe('Tier 3')
  })

  it('ignores programs that do not apply to the application', () => {
    const mixed = result({
      program_summaries: [
        program({ name: 'No PayNet', rank: 1, applicable: false, hard_failures: 0 }),
        program({ name: 'Standard', rank: 2, hard_failures: 2 }),
      ],
    })
    expect(defaultProgram(mixed)).toBe('Standard')
  })

  it('falls back to the first program when none apply, so the note can explain why', () => {
    const none = result({
      program_summaries: [program({ name: 'Medical', applicable: false })],
    })
    expect(defaultProgram(none)).toBe('Medical')
  })

  it('returns null for a lender whose policy could not be evaluated', () => {
    expect(defaultProgram(result({ status: 'error' }))).toBeNull()
  })
})
