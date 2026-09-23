import { Link } from 'react-router-dom'

const SECTIONS = [
  {
    to: '/applications',
    title: 'Applications',
    hint: 'Equipment finance requests and their lender matches.',
  },
  {
    to: '/lenders',
    title: 'Lenders',
    hint: 'Credit policies as data: programs, rules and restrictions for each lender.',
  },
]

export function Home() {
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      {SECTIONS.map((section) => (
        <Link
          key={section.to}
          to={section.to}
          className="group flex flex-col justify-between rounded-lg border border-slate-200 bg-white p-8 transition-colors hover:border-slate-900"
        >
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{section.title}</h2>
            <p className="mt-2 text-sm text-slate-500">{section.hint}</p>
          </div>
          <span className="mt-6 text-sm font-medium text-slate-500 group-hover:text-slate-900">
            View {section.title.toLowerCase()} →
          </span>
        </Link>
      ))}
    </div>
  )
}
