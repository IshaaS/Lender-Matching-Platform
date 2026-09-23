import { useNavigate } from 'react-router-dom'
import { useApplications } from '../api/hooks'
import { EmptyState, ErrorBanner, LinkButton, Loading, PageHeader, StatusBadge } from '../components/ui'
import { dateTime, humanize, money } from '../lib/format'

export function ApplicationsList() {
  const applications = useApplications()
  const navigate = useNavigate()

  return (
    <>
      <PageHeader
        title="Applications"
        subtitle="Equipment finance requests and their lender matches."
        back={{ to: '/', label: 'Home' }}
        actions={
          <LinkButton to="/applications/new" variant="primary">
            New application
          </LinkButton>
        }
      />
      {applications.isPending && <Loading label="Loading applications…" />}
      <ErrorBanner error={applications.error} title="Could not load applications" />
      {applications.data?.length === 0 && (
        <EmptyState
          title="No applications yet"
          hint="Create one from scratch, or start from a sample to see lender matching in action."
          action={
            <LinkButton to="/applications/new" variant="primary">
              New application
            </LinkButton>
          }
        />
      )}
      {applications.data && applications.data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500">
              <tr>
                {['Business', 'Industry', 'Amount', 'Status', 'Best match', 'Created'].map((h) => (
                  <th key={h} className="px-4 py-2.5 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {applications.data.map((a) => (
                <tr
                  key={a.id}
                  onClick={() => navigate(`/applications/${a.id}`)}
                  className="cursor-pointer hover:bg-slate-50"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">{a.legal_name ?? 'Untitled draft'}</div>
                    {a.notes && <div className="text-xs text-slate-500">{a.notes}</div>}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {humanize(a.industry)}
                    {a.state && <span className="text-slate-400"> · {a.state}</span>}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-slate-900">{money(a.amount)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={a.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {a.latest_run?.status === 'completed' ? (
                      a.latest_run.best_lender ? (
                        <>
                          <span className="font-medium text-slate-900">{a.latest_run.best_lender}</span>
                          <span className="text-slate-400">
                            {' '}
                            · {a.latest_run.eligible_count}/{a.latest_run.lender_count} eligible
                          </span>
                        </>
                      ) : (
                        <span className="text-red-700">No eligible lenders</span>
                      )
                    ) : a.latest_run?.status === 'failed' ? (
                      <span className="text-red-700">Run failed</span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{dateTime(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
