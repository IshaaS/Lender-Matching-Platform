import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useIngestionJobs, useLenders, useRetryIngestion, useUploadGuidelines } from '../api/hooks'
import type { IngestionJob } from '../api/types'
import { dateTime } from '../lib/format'
import { Pill } from '../pages/LendersList'
import { Button, ErrorBanner, Spinner } from './ui'

const INPUT =
  'block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-2 focus:outline-slate-900'

/**
 * The defined process for supporting a new lender: upload the guideline PDF, the extractor
 * proposes a draft policy, a person reviews it in the editor, then publishes. Nothing that
 * comes out of extraction is ever live without that review.
 */
export function OnboardFromPdf({ onClose }: { onClose: () => void }) {
  const lenders = useLenders()
  const upload = useUploadGuidelines()
  const [file, setFile] = useState<File | null>(null)
  const [target, setTarget] = useState<string>('new')
  const [name, setName] = useState('')

  const ready = file && (target !== 'new' || name.trim())

  return (
    <div className="space-y-4 rounded-lg border border-slate-900 bg-white p-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-900">Onboard a lender from its guideline PDF</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Upload → the extractor drafts the policy (programs, rules, restrictions) → you review
          the checklist and edit → publish. The draft is never evaluated until you publish it.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="pdf" className="mb-1 block text-xs font-medium text-slate-700">
            Guideline PDF
          </label>
          <input
            id="pdf"
            type="file"
            accept="application/pdf"
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-2 file:text-sm file:font-medium file:text-white"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </div>
        <div>
          <label htmlFor="target" className="mb-1 block text-xs font-medium text-slate-700">
            Lender
          </label>
          <select id="target" className={INPUT} value={target} onChange={(event) => setTarget(event.target.value)}>
            <option value="new">New lender…</option>
            {lenders.data?.map((lender) => (
              <option key={lender.id} value={lender.id} disabled={Boolean(lender.draft_version)}>
                {lender.name}
                {lender.draft_version ? ' (has a draft — publish or discard it first)' : ''}
              </option>
            ))}
          </select>
        </div>
        {target === 'new' && (
          <div className="sm:col-span-2">
            <label htmlFor="new-name" className="mb-1 block text-xs font-medium text-slate-700">
              Lender name
            </label>
            <input
              id="new-name"
              className={INPUT}
              value={name}
              placeholder="As it appears on the document"
              onChange={(event) => setName(event.target.value)}
            />
          </div>
        )}
      </div>

      <ErrorBanner error={upload.error} />

      <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
        <Button onClick={onClose}>Close</Button>
        <Button
          variant="primary"
          busy={upload.isPending}
          disabled={!ready}
          onClick={() =>
            file &&
            upload.mutate(
              {
                file,
                lenderId: target === 'new' ? undefined : target,
                newLenderName: target === 'new' ? name.trim() : undefined,
              },
              { onSuccess: () => setFile(null) },
            )
          }
        >
          Upload and extract
        </Button>
      </div>

      <IngestionJobs />
    </div>
  )
}

const STATUS: Record<IngestionJob['status'], { label: string; tone: 'amber' | 'emerald' | 'red' | 'slate' }> = {
  uploaded: { label: 'Queued', tone: 'amber' },
  extracting: { label: 'Extracting', tone: 'amber' },
  draft_ready: { label: 'Draft ready', tone: 'emerald' },
  failed: { label: 'Failed', tone: 'red' },
}

function IngestionJobs() {
  const jobs = useIngestionJobs()
  const retry = useRetryIngestion()
  if (!jobs.data || jobs.data.length === 0) return null
  return (
    <div className="border-t border-slate-100 pt-3">
      <h3 className="mb-2 text-xs font-medium text-slate-500">Recent uploads</h3>
      <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">
        {jobs.data.slice(0, 8).map((job) => {
          const status = STATUS[job.status]
          const active = job.status === 'uploaded' || job.status === 'extracting'
          return (
            <li key={job.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-slate-900">
                  {job.lender_name ?? job.new_lender_name ?? 'Unnamed lender'}
                  <span className="font-normal text-slate-400"> · {job.filename}</span>
                </div>
                <div className="text-xs text-slate-500">
                  {dateTime(job.created_at)}
                  {job.extractor && ` · ${job.extractor} extractor`}
                  {job.mode === 'hatchet' && ' · Hatchet'}
                  {job.status === 'draft_ready' && ` · ${job.uncertainties.length} items to review`}
                </div>
                {job.error && <div className="mt-0.5 text-xs text-red-700">{job.error}</div>}
              </div>
              <span className="flex items-center gap-2">
                {active && <Spinner className="h-3.5 w-3.5 text-amber-600" />}
                <Pill tone={status.tone}>{status.label}</Pill>
              </span>
              {job.status === 'draft_ready' && job.lender_id && (
                <Link
                  to={`/lenders/${job.lender_id}?v=${job.policy_version_id}`}
                  className="text-xs font-medium text-slate-900 underline underline-offset-4"
                >
                  Review draft →
                </Link>
              )}
              {job.status === 'failed' && (
                <Button variant="ghost" className="!px-2 text-xs" busy={retry.isPending} onClick={() => retry.mutate(job.id)}>
                  Retry
                </Button>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
