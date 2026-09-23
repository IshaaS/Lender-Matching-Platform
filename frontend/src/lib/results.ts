import type { MatchResultSummary, ProgramSummary } from '../api/types'

/**
 * Which program to show first for a lender: the one that matched, else the one the applicant
 * came closest to. Ties go to the least demanding tier (highest rank number) so the criteria
 * on screen show the lowest bar the applicant could clear, matching the engine's rejection
 * reasons rather than contradicting them.
 */
export function defaultProgram(result: MatchResultSummary): string | null {
  if (result.matched_program_name) return result.matched_program_name
  const applicable = result.program_summaries.filter((p) => p.applicable)
  const closest = [...applicable].sort(
    (a, b) => a.hard_failures - b.hard_failures || b.rank - a.rank,
  )[0]
  return closest?.name ?? result.program_summaries[0]?.name ?? null
}

export const programTone = (summary: ProgramSummary, matched: boolean): string => {
  if (!summary.applicable) return 'text-slate-400 border-slate-200'
  if (matched) {
    if (summary.decision === 'manual_review' || summary.decision_mode === 'manual_review') {
      return 'text-amber-800 border-amber-300 bg-amber-50'
    }
    if (summary.decision === 'needs_information') {
      return 'text-blue-800 border-blue-300 bg-blue-50'
    }
    return 'text-emerald-800 border-emerald-300 bg-emerald-50'
  }
  return summary.hard_failures > 0 ? 'text-red-800 border-red-200' : 'text-slate-700 border-slate-300'
}
