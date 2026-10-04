import { api } from './api'

export type Frequency = 'monthly' | 'quarterly' | 'yearly'
export type Kind = 'income' | 'expense'

export interface Category {
  id: number
  name: string
  kind: Kind
  parent_id: number | null
}

export interface Version {
  id: number
  amount: number
  frequency: Frequency
  monthly: number
  valid_from: string
  valid_to: string | null
  locked: boolean
}

export interface Item {
  id: number
  name: string
  category_id: number
  category_name: string
  kind: Kind
  active: Version | null
  versions: Version[]
}

export interface Group {
  category_id: number
  name: string
  kind: Kind
  total: number
  children: Group[]
}

export interface FinancingFlow {
  financing_id: number
  name: string
  interest: number
  principal: number
  saving: number
  fee: number
  total: number
}

export interface Summary {
  month: string
  income: number
  expenses: number // running costs without financings
  financing: number
  financing_flows: FinancingFlow[]
  balance: number
  savings_rate: number | null
  income_groups: Group[]
  expense_groups: Group[]
}

export interface Sankey {
  month: string
  nodes: {
    id: string
    name: string
    kind: 'income' | 'hub' | 'expense' | 'financing' | 'purpose' | 'surplus' | 'deficit'
  }[]
  links: { source: string; target: string; value: number }[]
}

export interface SeriesPoint {
  month: string
  income: number
  expenses: number
  financing: number
  balance: number
}

export interface AuditEntry {
  id: number
  action: string
  entity: string
  entity_id: number
  reason: string | null
  created_at: string
  user_name: string
  subject: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
}

export const cashflowApi = {
  categories: () => api<Category[]>('/categories'),
  items: (month: string) => api<Item[]>(`/cashflow/items?month=${month}`),
  summary: (month: string) => api<Summary>(`/cashflow/summary?month=${month}`),
  sankey: (month: string) => api<Sankey>(`/cashflow/sankey?month=${month}`),
  series: (from: string, to: string) => api<SeriesPoint[]>(`/cashflow/series?from=${from}&to=${to}`),
  audit: () => api<AuditEntry[]>('/audit?limit=30'),
  createItem: (json: {
    name: string
    category_id: number
    amount: string
    frequency: Frequency
    valid_from: string
  }) => api<Item>('/cashflow/items', { method: 'POST', json }),
  changeItem: (id: number, json: { effective_from: string; amount: string; frequency: Frequency }) =>
    api<Item>(`/cashflow/items/${id}/change`, { method: 'POST', json }),
  endItem: (id: number, json: { end_from: string }) => api<Item>(`/cashflow/items/${id}/end`, { method: 'POST', json }),
  correctVersion: (id: number, json: { reason: string; amount?: string; frequency?: Frequency }) =>
    api<Item>(`/cashflow/versions/${id}/correct`, { method: 'POST', json }),
}
