import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { type FieldPath, FormProvider, useFieldArray, useForm, useWatch } from 'react-hook-form'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { useApplication, useCatalog, useSamples, useSaveApplication } from '../api/hooks'
import type { Application, ApplicationPayload, FieldIssue } from '../api/types'
import {
  CheckField,
  DateField,
  Grid,
  NumberField,
  SelectField,
  TextField,
  YesNoField,
} from '../components/form'
import { Button, Card, ErrorBanner, Loading, PageHeader } from '../components/ui'
import {
  applicationSchema,
  CDL_EQUIPMENT,
  emptyApplication,
  emptyEquipment,
  emptyGuarantor,
  MEDICAL_INDUSTRIES,
  toPayload,
} from '../lib/applicationForm'

const HISTORY_FLAGS = [
  ['has_bankruptcy', 'Bankruptcy'],
  ['has_judgments', 'Judgments'],
  ['has_foreclosures', 'Foreclosures'],
  ['has_repossessions', 'Repossessions'],
  ['has_tax_liens', 'Tax liens'],
  ['has_recent_collections', 'Collections / charge-offs (last 3 yrs)'],
] as const

export function ApplicationForm() {
  const { id } = useParams()
  const navigate = useNavigate()
  const existing = useApplication(id)
  const catalog = useCatalog()
  const samples = useSamples()
  const save = useSaveApplication(id)
  const [submitError, setSubmitError] = useState<unknown>(null)
  const [submitting, setSubmitting] = useState(false)

  const form = useForm<ApplicationPayload>({
    resolver: zodResolver(applicationSchema),
    defaultValues: emptyApplication(),
    mode: 'onBlur',
  })
  const { control, reset, handleSubmit, setError } = form
  const guarantors = useFieldArray({ control, name: 'guarantors' })
  const equipment = useFieldArray({ control, name: 'equipment' })

  const industry = useWatch({ control, name: 'business.industry' })
  const corpOnly = useWatch({ control, name: 'loan.corp_only' })
  const equipmentValues = useWatch({ control, name: 'equipment' })
  const guarantorValues = useWatch({ control, name: 'guarantors' })

  const isTrucking = industry === 'trucking'
  const isMedical = MEDICAL_INDUSTRIES.includes(industry ?? '')
  const needsCdl =
    isTrucking || equipmentValues.some((item) => CDL_EQUIPMENT.includes(item.category ?? ''))

  useEffect(() => {
    if (!existing.data) return
    // keepErrors: a rejected submit sets per-field errors, and the refetch that follows must
    // not wipe them. keepDirtyValues: never overwrite what the user is still typing.
    reset(toPayload(existing.data), { keepErrors: true, keepDirtyValues: true })
  }, [existing.data, reset])

  const options = (key: string) => catalog.data?.fields.find((f) => f.key === key)?.options ?? []

  // Hidden sections must not leak stale values into the payload.
  const clean = (values: ApplicationPayload): ApplicationPayload => ({
    ...values,
    guarantors: values.loan.corp_only ? [] : values.guarantors,
  })

  const saveDraft = handleSubmit(async (values) => {
    setSubmitError(null)
    const saved = await save.mutateAsync(clean(values))
    navigate(`/applications/${saved.id}`)
  })

  const saveAndSubmit = handleSubmit(async (values) => {
    setSubmitError(null)
    setSubmitting(true)
    let saved: Application | undefined
    try {
      saved = await save.mutateAsync(clean(values))
      await api<Application>(`/applications/${saved.id}/submit`, { method: 'POST' })
      navigate(`/applications/${saved.id}`)
    } catch (error) {
      setSubmitError(error)
      // The draft itself was saved: keep editing that record rather than creating another.
      if (saved && !id) navigate(`/applications/${saved.id}/edit`, { replace: true })
      if (error instanceof ApiError && error.status === 422) {
        const issues = (error.detail as { errors?: FieldIssue[] } | null)?.errors ?? []
        for (const issue of issues) {
          setError(issue.path as FieldPath<ApplicationPayload>, { message: 'Required to submit' })
        }
      }
    } finally {
      setSubmitting(false)
    }
  })

  if (id && existing.isPending) return <Loading label="Loading application…" />
  if (id && existing.error) return <ErrorBanner error={existing.error} />
  if (existing.data && existing.data.status !== 'draft') {
    return <Navigate to={`/applications/${id}`} replace />
  }

  return (
    <FormProvider {...form}>
      <form onSubmit={(event) => event.preventDefault()} noValidate>
        <PageHeader
          title={id ? 'Edit application' : 'New application'}
          subtitle="Save a partial draft at any time. Everything needed for underwriting is checked on submit."
          back={{ to: id ? `/applications/${id}` : '/applications', label: 'Back' }}
        />

        {!id && samples.data && (
          <div className="mb-5 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-3">
            <span className="mr-1 text-xs font-medium text-slate-500">Start from a sample:</span>
            {samples.data.map((sample) => (
              <Button
                key={sample.key}
                variant="ghost"
                className="!px-2.5 !py-1 text-xs"
                onClick={() => reset(sample.payload)}
              >
                {sample.title}
              </Button>
            ))}
          </div>
        )}

        <div className="space-y-5">
          <Card title="Business">
            <Grid>
              <TextField name="business.legal_name" label="Legal name" />
              <SelectField name="business.entity_type" label="Entity type" options={options('entity_type')} />
              <SelectField name="business.industry" label="Industry" options={options('industry')} />
              <SelectField name="business.state" label="State" options={options('business_state')} />
              <NumberField name="business.years_in_business" label="Time in business" suffix="years" />
              <NumberField name="business.annual_revenue" label="Annual revenue" prefix="$" />
              <YesNoField name="business.has_physical_location" label="Has a physical location" />
              <YesNoField name="business.is_us_based" label="US-based business" />
              {isTrucking && (
                <NumberField
                  name="business.trucks_operated"
                  label="Trucks currently operated"
                  step="1"
                  hint="Trucking programs depend on fleet size."
                />
              )}
            </Grid>
          </Card>

          <Card title="Loan request">
            <Grid>
              <NumberField name="loan.amount" label="Amount requested" prefix="$" />
              <NumberField name="loan.term_months" label="Term" suffix="months" step="1" />
              <SelectField name="loan.transaction_type" label="Transaction type" options={options('transaction_type')} />
              <NumberField name="loan.down_payment_pct" label="Down payment" suffix="%" />
              <NumberField name="loan.soft_cost_pct" label="Soft costs" suffix="%" hint="Share of the amount that is not hard collateral." />
            </Grid>
            <div className="mt-4">
              <CheckField name="loan.corp_only" label="Corp only — no owner will personally guarantee" />
            </div>
          </Card>

          <Card
            title="Equipment"
            actions={
              <Button variant="ghost" onClick={() => equipment.append(emptyEquipment())}>
                + Add item
              </Button>
            }
          >
            <div className="space-y-5">
              {equipment.fields.map((field, index) => (
                <div key={field.id} className={index > 0 ? 'border-t border-slate-100 pt-5' : ''}>
                  <Grid>
                    <SelectField name={`equipment.${index}.category`} label="Equipment type" options={options('equipment_category')} />
                    <TextField name={`equipment.${index}.description`} label="Description" placeholder="Make / model" />
                    <NumberField name={`equipment.${index}.model_year`} label="Model year" step="1" />
                    <SelectField name={`equipment.${index}.condition`} label="Condition" options={options('equipment_condition')} />
                    <NumberField name={`equipment.${index}.mileage`} label="Mileage" suffix="mi" step="1" />
                    <NumberField name={`equipment.${index}.hours`} label="Hours" step="1" />
                    <YesNoField name={`equipment.${index}.is_titled`} label="Titled asset" />
                  </Grid>
                  {equipment.fields.length > 1 && (
                    <Button variant="ghost" className="mt-3 !px-2 text-xs text-red-700" onClick={() => equipment.remove(index)}>
                      Remove item
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </Card>

          {!corpOnly && (
            <Card
              title="Personal guarantors"
              hint="Owners with 10% or more. Lenders underwrite to the weakest guarantor."
              actions={
                <Button variant="ghost" onClick={() => guarantors.append(emptyGuarantor())}>
                  + Add guarantor
                </Button>
              }
            >
              <div className="space-y-6">
                {guarantors.fields.map((field, index) => (
                  <div key={field.id} className={index > 0 ? 'border-t border-slate-100 pt-6' : ''}>
                    <Grid>
                      <TextField name={`guarantors.${index}.full_name`} label="Full name" />
                      <NumberField name={`guarantors.${index}.ownership_pct`} label="Ownership" suffix="%" />
                      <NumberField name={`guarantors.${index}.fico_score`} label="FICO score" step="1" />
                      <YesNoField name={`guarantors.${index}.is_homeowner`} label="Homeowner" />
                      <NumberField name={`guarantors.${index}.years_at_residence`} label="Years at current residence" />
                      <YesNoField name={`guarantors.${index}.is_us_citizen`} label="US citizen" />
                      <NumberField name={`guarantors.${index}.industry_experience_years`} label="Industry experience" suffix="years" />
                      <NumberField name={`guarantors.${index}.revolving_credit_limit`} label="Revolving credit limit" prefix="$" />
                      <NumberField name={`guarantors.${index}.revolving_balance`} label="Revolving balance" prefix="$" />
                      <NumberField name={`guarantors.${index}.unsecured_debt`} label="Unsecured debt" prefix="$" hint="Excluding student loans." />
                      {needsCdl && (
                        <>
                          <YesNoField name={`guarantors.${index}.has_cdl`} label="Holds a CDL" />
                          <SelectField name={`guarantors.${index}.cdl_class`} label="CDL class" options={['A', 'B', 'C']} />
                          <NumberField name={`guarantors.${index}.cdl_years`} label="Years holding CDL" />
                        </>
                      )}
                      {isMedical && (
                        <>
                          <YesNoField name={`guarantors.${index}.is_licensed_medical_professional`} label="Licensed medical professional" />
                          <NumberField name={`guarantors.${index}.years_licensed`} label="Years licensed" />
                        </>
                      )}
                    </Grid>
                    <fieldset className="mt-4">
                      <legend className="mb-2 text-xs font-medium text-slate-700">Credit history on record</legend>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                        {HISTORY_FLAGS.map(([key, label]) => (
                          <CheckField key={key} name={`guarantors.${index}.${key}`} label={label} />
                        ))}
                      </div>
                    </fieldset>
                    {guarantorValues[index]?.has_bankruptcy && (
                      <div className="mt-4 max-w-xs">
                        <DateField
                          name={`guarantors.${index}.bankruptcy_discharge_date`}
                          label="Bankruptcy discharge date"
                          hint="Leave empty if not yet discharged."
                        />
                      </div>
                    )}
                    {guarantors.fields.length > 1 && (
                      <Button variant="ghost" className="mt-3 !px-2 text-xs text-red-700" onClick={() => guarantors.remove(index)}>
                        Remove guarantor
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card title="Business credit" hint="Leave PayNet empty if the business has no score — some lenders have a separate program for that.">
            <Grid>
              <NumberField name="business_credit.paynet_score" label="PayNet MasterScore" step="1" />
              <NumberField name="business_credit.largest_comparable_credit" label="Largest comparable credit" prefix="$" hint="Biggest similar loan or lease repaid. Enter 0 if none." />
              <NumberField name="business_credit.comparable_contracts_count" label="Comparable contracts (12 mo)" step="1" hint="$10K+ contracts with recent payment activity." />
              <NumberField name="business_credit.trade_lines_count" label="Trade lines" step="1" />
              <NumberField name="business_credit.trade_history_years" label="Trade history" suffix="years" />
              <NumberField name="business_credit.clean_payment_history_months" label="Clean payment history" suffix="months" step="1" />
            </Grid>
          </Card>

          <ErrorBanner error={submitError ?? save.error} title={submitError ? 'Saved as draft, but it cannot be submitted yet' : undefined} />

          <div className="sticky bottom-0 -mx-4 flex justify-end gap-2 border-t border-slate-200 bg-slate-50/95 px-4 py-3 backdrop-blur">
            <Button onClick={() => navigate(id ? `/applications/${id}` : '/applications')}>Cancel</Button>
            <Button onClick={saveDraft} busy={save.isPending && !submitting}>
              Save draft
            </Button>
            <Button variant="primary" onClick={saveAndSubmit} busy={submitting}>
              Save &amp; submit
            </Button>
          </div>
        </div>
      </form>
    </FormProvider>
  )
}
