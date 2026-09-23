import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import type { ApplicationStatus, RunStatus } from '../api/types'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-400',
  secondary: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50',
  danger: 'border border-red-200 bg-white text-red-700 hover:bg-red-50 disabled:opacity-50',
  ghost: 'text-slate-600 hover:bg-slate-100 disabled:opacity-50',
}

const BUTTON_BASE =
  'inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  busy?: boolean
}

export function Button({ variant = 'secondary', busy, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || busy}
      className={`${BUTTON_BASE} ${VARIANTS[variant]} ${rest.className ?? ''}`}
    >
      {busy && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  )
}

export function LinkButton(props: { to: string; variant?: Variant; children: ReactNode }) {
  return (
    <Link to={props.to} className={`${BUTTON_BASE} ${VARIANTS[props.variant ?? 'secondary']}`}>
      {props.children}
    </Link>
  )
}

export function Spinner({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" opacity=".25" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="4" />
    </svg>
  )
}

export function Card(props: { title?: string; hint?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      {(props.title || props.actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-3.5">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">{props.title}</h2>
            {props.hint && <p className="mt-0.5 text-xs text-slate-500">{props.hint}</p>}
          </div>
          {props.actions}
        </header>
      )}
      <div className="p-5">{props.children}</div>
    </section>
  )
}

export function PageHeader(props: { title: string; subtitle?: ReactNode; actions?: ReactNode; back?: { to: string; label: string } }) {
  return (
    <div className="mb-6">
      {props.back && (
        <Link to={props.back.to} className="text-xs font-medium text-slate-500 hover:text-slate-800">
          ← {props.back.label}
        </Link>
      )}
      <div className="mt-1 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{props.title}</h1>
          {props.subtitle && <div className="mt-1 text-sm text-slate-500">{props.subtitle}</div>}
        </div>
        <div className="flex flex-wrap gap-2">{props.actions}</div>
      </div>
    </div>
  )
}

const BADGE: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-700',
  submitted: 'bg-blue-100 text-blue-800',
  underwriting: 'bg-amber-100 text-amber-800',
  queued: 'bg-amber-100 text-amber-800',
  running: 'bg-amber-100 text-amber-800',
  completed: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
}

export function StatusBadge({ status }: { status: ApplicationStatus | RunStatus }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${BADGE[status]}`}>
      {(status === 'underwriting' || status === 'queued' || status === 'running') && (
        <Spinner className="h-3 w-3" />
      )}
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
      <Spinner /> {label}
    </div>
  )
}

/** One place that knows the API error shape: a message plus optional per-field issues. */
export function ErrorBanner({ error, title }: { error: unknown; title?: string }) {
  if (!error) return null
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  const issues =
    error instanceof ApiError && error.detail && typeof error.detail === 'object' && 'errors' in error.detail
      ? ((error.detail as { errors: unknown }).errors as { path?: string; label?: string }[] | string[])
      : []
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      <p className="font-medium">{title ?? message}</p>
      {title && <p className="mt-0.5">{message}</p>}
      {issues.length > 0 && (
        <ul className="mt-2 list-inside list-disc space-y-0.5 text-red-700">
          {issues.slice(0, 12).map((issue, index) => (
            <li key={index}>{typeof issue === 'string' ? issue : (issue.label ?? issue.path)}</li>
          ))}
          {issues.length > 12 && <li>…and {issues.length - 12} more</li>}
        </ul>
      )}
    </div>
  )
}

export function EmptyState(props: { title: string; hint: string; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
      <h2 className="text-base font-semibold text-slate-900">{props.title}</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">{props.hint}</p>
      {props.action && <div className="mt-5 flex justify-center">{props.action}</div>}
    </div>
  )
}

export function DataList({ items }: { items: [label: string, value: ReactNode][] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs text-slate-500">{label}</dt>
          <dd className="mt-0.5 text-sm font-medium text-slate-900">{value ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}
