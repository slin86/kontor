import { api } from './api'
import { personQuery } from './peopleApi'

export type FinancingKind = 'loan' | 'building_savings' | 'credit_line'
export type Phase = 'not_started' | 'saving' | 'loan' | 'finished'

export interface Financing {
  id: number
  person_id: number
  kind: FinancingKind
  name: string
  purpose: string | null
  start: string
  end_month: string // first month without any payment
  regular_payment: number
  payment_this_month: number
  phase: Phase
  remaining_debt: number | null
  saved: number | null
  prefinanced: boolean // Bausparfinanzierung: advance loan next to the savings phase
  total_interest: number
  remaining_interest: number
  credit_limit: number | null // credit line only
  available: number | null // credit line only: what can still be drawn
}

export interface ScheduleRow {
  month: string
  interest: number
  principal: number
  saving: number
  fee: number
  balance: number
  phase: 'saving' | 'loan'
  special: number
  drawn: number
}

export interface FinancingEvent {
  id: number
  month: string
  kind: 'special_repayment' | 'payment_change' | 'rate_change' | 'drawdown' | 'payout' | 'deposit'
  value: number // euros, or percent per year for rate changes
  locked: boolean
}

export interface FinancingDetail extends Financing {
  input: Record<string, string | null>
  events: FinancingEvent[]
  schedule: ScheduleRow[]
}

export interface OutlookPoint {
  month: string
  income: number
  expenses: number
  financing: number
  free: number
}

export interface OutlookEvent {
  month: string
  kind: 'financing_end' | 'item_end'
  label: string
  monthly_change: number
}

export interface Outlook {
  start: string
  years: number
  income_growth_percent: number
  expense_growth_percent: number
  points: OutlookPoint[]
  events: OutlookEvent[]
}

export type LoanInput = {
  kind: 'loan'
  name: string
  purpose: 'real_estate' | 'consumer' | 'zero_percent' | 'other'
  principal: string
  annual_rate_percent: string
  monthly_payment?: string
  initial_repayment_percent?: string
  start: string
}

export type Payout = { month: string; amount: string }

export type BausparInput = {
  kind: 'building_savings'
  name: string
  contract_sum: string
  monthly_saving: string
  start: string
  allocation: string
  fee_percent?: string
  fee_amount?: string // the fee in euros instead of fee_percent
  deposit_rate_percent: string
  prefinance_rate_percent?: string // set for a Bausparfinanzierung
  payouts?: Payout[] // staged payouts of the advance loan
  loan_rate_percent: string
  loan_payment: string
}

export type CreditLineInput = {
  kind: 'credit_line'
  name: string
  limit: string
  balance: string
  annual_rate_percent: string
  monthly_payment: string
  start: string
}

export type FinancingInput = LoanInput | BausparInput | CreditLineInput

export const financingApi = {
  list: (person: number | null) => api<Financing[]>(`/financings${personQuery(person, true)}`),
  get: (id: number) => api<FinancingDetail>(`/financings/${id}`),
  create: (json: FinancingInput, person?: number) =>
    api<FinancingDetail>(`/financings${personQuery(person ?? null, true)}`, { method: 'POST', json }),
  remove: (id: number) => api<void>(`/financings/${id}`, { method: 'DELETE' }),
  correct: (id: number, json: { reason: string; data: FinancingInput }) =>
    api<FinancingDetail>(`/financings/${id}/correct`, { method: 'POST', json }),
  addEvent: (id: number, json: { month: string; kind: FinancingEvent['kind']; value: string }) =>
    api<FinancingDetail>(`/financings/${id}/events`, { method: 'POST', json }),
  removeEvent: (id: number, eventId: number) =>
    api<FinancingDetail>(`/financings/${id}/events/${eventId}`, { method: 'DELETE' }),
  outlook: (years: number, incomeGrowth: number, expenseGrowth: number, person: number | null) =>
    api<Outlook>(`/outlook?years=${years}&income_growth=${incomeGrowth}&expense_growth=${expenseGrowth}${personQuery(person)}`),
}
