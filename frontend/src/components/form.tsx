import type { ReactNode } from 'react'
import { type FieldPath, useFormContext } from 'react-hook-form'
import type { ApplicationPayload } from '../api/types'
import { humanize } from '../lib/format'

type Name = FieldPath<ApplicationPayload>

const INPUT =
  'block w-full rounded-md border bg-white px-3 py-2 text-sm text-slate-900 shadow-xs placeholder:text-slate-400 focus:outline-2 focus:outline-offset-0 focus:outline-slate-900'
const border = (invalid: boolean) => (invalid ? 'border-red-400' : 'border-slate-300')

// Empty inputs become null (the API's "not provided"), never "" or NaN.
const asText = (value: unknown) => (value === '' || value == null ? null : String(value))
const asNumber = (value: unknown) => (value === '' || value == null ? null : Number(value))
const asFlag = (value: unknown) =>
  value === 'true' || value === true ? true : value === 'false' || value === false ? false : null

function useField(name: Name) {
  const { register, getFieldState, formState } = useFormContext<ApplicationPayload>()
  return { register, error: getFieldState(name, formState).error?.message }
}

function Wrapper(props: { label: string; name: string; error?: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={props.name} className="mb-1 block text-xs font-medium text-slate-700">
        {props.label}
      </label>
      {props.children}
      {props.error ? (
        <p className="mt-1 text-xs text-red-600">{props.error}</p>
      ) : (
        props.hint && <p className="mt-1 text-xs text-slate-400">{props.hint}</p>
      )}
    </div>
  )
}

interface BaseProps {
  name: Name
  label: string
  hint?: string
}

export function TextField({ name, label, hint, placeholder }: BaseProps & { placeholder?: string }) {
  const { register, error } = useField(name)
  return (
    <Wrapper label={label} name={name} error={error} hint={hint}>
      <input
        id={name}
        type="text"
        placeholder={placeholder}
        className={`${INPUT} ${border(Boolean(error))}`}
        {...register(name, { setValueAs: asText })}
      />
    </Wrapper>
  )
}

export function NumberField(props: BaseProps & { prefix?: string; suffix?: string; step?: string }) {
  const { register, error } = useField(props.name)
  return (
    <Wrapper label={props.label} name={props.name} error={error} hint={props.hint}>
      <div className="relative">
        {props.prefix && (
          <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-slate-400">
            {props.prefix}
          </span>
        )}
        <input
          id={props.name}
          type="number"
          inputMode="decimal"
          step={props.step ?? 'any'}
          className={`${INPUT} ${border(Boolean(error))} ${props.prefix ? 'pl-7' : ''} ${props.suffix ? 'pr-12' : ''}`}
          {...register(props.name, { setValueAs: asNumber })}
        />
        {props.suffix && (
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-slate-400">
            {props.suffix}
          </span>
        )}
      </div>
    </Wrapper>
  )
}

export function DateField({ name, label, hint }: BaseProps) {
  const { register, error } = useField(name)
  return (
    <Wrapper label={label} name={name} error={error} hint={hint}>
      <input
        id={name}
        type="date"
        className={`${INPUT} ${border(Boolean(error))}`}
        {...register(name, { setValueAs: asText })}
      />
    </Wrapper>
  )
}

export function SelectField({ name, label, hint, options }: BaseProps & { options: readonly string[] }) {
  const { register, error } = useField(name)
  return (
    <Wrapper label={label} name={name} error={error} hint={hint}>
      <select
        id={name}
        className={`${INPUT} ${border(Boolean(error))}`}
        {...register(name, { setValueAs: asText })}
      >
        <option value="">Select…</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {humanize(option)}
          </option>
        ))}
      </select>
    </Wrapper>
  )
}

/** Tri-state: unanswered is different from "No" for lender rules, so it stays distinct. */
export function YesNoField({ name, label, hint }: BaseProps) {
  const { register, error } = useField(name)
  return (
    <Wrapper label={label} name={name} error={error} hint={hint}>
      <select
        id={name}
        className={`${INPUT} ${border(Boolean(error))}`}
        {...register(name, { setValueAs: asFlag })}
      >
        <option value="">Select…</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    </Wrapper>
  )
}

export function CheckField({ name, label }: { name: Name; label: string }) {
  const { register } = useField(name)
  return (
    <label className="flex items-center gap-2 text-sm text-slate-700">
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-slate-300 accent-slate-900"
        {...register(name)}
      />
      {label}
    </label>
  )
}

export function Grid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
}
