import { z } from 'zod'
import type { ApplicationPayload, EquipmentPayload, GuarantorPayload } from '../api/types'

// Client-side checks mirror the API's ranges so mistakes surface while typing. Required-ness
// is NOT enforced here: drafts may be partial, and the server reports completeness on submit.
const num = (min: number, max: number, what: string) =>
  z
    .number({ error: 'Enter a number' })
    .min(min, `${what} must be at least ${min.toLocaleString()}`)
    .max(max, `${what} must be at most ${max.toLocaleString()}`)
    .nullable()
const int = (min: number, max: number, what: string) =>
  z
    .number({ error: 'Enter a number' })
    .int('Whole numbers only')
    .min(min, `${what} must be at least ${min.toLocaleString()}`)
    .max(max, `${what} must be at most ${max.toLocaleString()}`)
    .nullable()
const text = (max: number) => z.string().max(max).nullable()
const flag = z.boolean().nullable()
const money = num(0, 1_000_000_000, 'Amount')
const percent = num(0, 100, 'Percentage')
const years = num(0, 150, 'Years')

const thisYear = new Date().getFullYear()

export const applicationSchema = z.object({
  business: z.object({
    legal_name: text(200),
    entity_type: text(50),
    state: text(2),
    industry: text(60),
    years_in_business: years,
    annual_revenue: money,
    has_physical_location: flag,
    is_us_based: flag,
    trucks_operated: int(0, 100_000, 'Trucks'),
  }),
  loan: z.object({
    amount: num(1, 1_000_000_000, 'Amount'),
    term_months: int(1, 240, 'Term'),
    transaction_type: text(30),
    down_payment_pct: percent,
    soft_cost_pct: percent,
    corp_only: z.boolean(),
    notes: text(2000),
  }),
  business_credit: z.object({
    paynet_score: int(300, 900, 'PayNet score'),
    trade_lines_count: int(0, 100_000, 'Trade lines'),
    trade_history_years: years,
    largest_comparable_credit: money,
    comparable_contracts_count: int(0, 100_000, 'Contracts'),
    clean_payment_history_months: int(0, 1200, 'Months'),
  }),
  guarantors: z.array(
    z.object({
      full_name: text(200),
      ownership_pct: percent,
      fico_score: int(300, 850, 'FICO score'),
      is_homeowner: flag,
      years_at_residence: years,
      is_us_citizen: flag,
      industry_experience_years: years,
      has_cdl: flag,
      cdl_class: text(1),
      cdl_years: years,
      is_licensed_medical_professional: flag,
      years_licensed: years,
      revolving_credit_limit: money,
      revolving_balance: money,
      unsecured_debt: money,
      has_bankruptcy: z.boolean(),
      bankruptcy_discharge_date: z.string().nullable(),
      has_judgments: z.boolean(),
      has_foreclosures: z.boolean(),
      has_repossessions: z.boolean(),
      has_tax_liens: z.boolean(),
      has_recent_collections: z.boolean(),
    }),
  ),
  equipment: z.array(
    z.object({
      category: text(60),
      description: text(300),
      model_year: int(1950, thisYear + 1, 'Model year'),
      condition: text(10),
      mileage: int(0, 5_000_000, 'Mileage'),
      hours: int(0, 1_000_000, 'Hours'),
      is_titled: flag,
    }),
  ),
}) satisfies z.ZodType<ApplicationPayload>

export const emptyGuarantor = (): GuarantorPayload => ({
  full_name: null, ownership_pct: null, fico_score: null, is_homeowner: null,
  years_at_residence: null, is_us_citizen: null, industry_experience_years: null,
  has_cdl: null, cdl_class: null, cdl_years: null, is_licensed_medical_professional: null,
  years_licensed: null, revolving_credit_limit: null, revolving_balance: null,
  unsecured_debt: null, has_bankruptcy: false, bankruptcy_discharge_date: null,
  has_judgments: false, has_foreclosures: false, has_repossessions: false,
  has_tax_liens: false, has_recent_collections: false,
})

export const emptyEquipment = (): EquipmentPayload => ({
  category: null, description: null, model_year: null, condition: null, mileage: null,
  hours: null, is_titled: null,
})

export const emptyApplication = (): ApplicationPayload => ({
  business: {
    legal_name: null, entity_type: null, state: null, industry: null, years_in_business: null,
    annual_revenue: null, has_physical_location: null, is_us_based: null, trucks_operated: null,
  },
  loan: {
    amount: null, term_months: null, transaction_type: null, down_payment_pct: null,
    soft_cost_pct: null, corp_only: false, notes: null,
  },
  business_credit: {
    paynet_score: null, trade_lines_count: null, trade_history_years: null,
    largest_comparable_credit: null, comparable_contracts_count: null,
    clean_payment_history_months: null,
  },
  guarantors: [emptyGuarantor()],
  equipment: [emptyEquipment()],
})

/** Strips server-only fields (id, status, ...) so an Application can seed the form. */
export const toPayload = (source: ApplicationPayload): ApplicationPayload => ({
  business: source.business,
  loan: source.loan,
  business_credit: source.business_credit,
  guarantors: source.guarantors,
  equipment: source.equipment,
})

export const MEDICAL_INDUSTRIES = ['medical', 'dental', 'veterinary']
export const CDL_EQUIPMENT = ['class_8_truck', 'dump_truck', 'medium_duty_truck']
