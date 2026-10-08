import { api } from './api'
import { personQuery } from './peopleApi'

export type Frequency = 'monthly' | 'quarterly' | 'yearly'
export type Kind = 'income' | 'expense'

export interface Category {
  id: number
  name: string
  kind: Kind
  parent_id: number | null
  item_count: number
  sort_order: number
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
  person_id: number
  transfer_to_id: number | null
  transfer_to_name: string | null
  incoming: boolean // a transfer seen from the person who receives it
  active: Version | null
  versions: Version[]
}

export interface Group {
  category_id: number
  name: string
  kind: Kind
  total: number
  children: Group[]
  direct?: boolean
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
  createCategory: (json: { name: string; kind: Kind; parent_id: number | null }) =>
    api<Category>('/categories', { method: 'POST', json }),
  updateCategory: (id: number, json: { name: string; parent_id: number | null }) =>
    api<Category>(`/categories/${id}`, { method: 'PUT', json }),
  moveCategory: (id: number, direction: 'up' | 'down') =>
    api<Category[]>(`/categories/${id}/move`, { method: 'POST', json: { direction } }),
  deleteCategory: (id: number, moveTo: number | null) =>
    api<void>(`/categories/${id}${moveTo === null ? '' : `?move_to=${moveTo}`}`, { method: 'DELETE' }),
  items: (month: string, person: number | null) =>
    api<Item[]>(`/cashflow/items?month=${month}${personQuery(person)}`),
  summary: (month: string, person: number | null) =>
    api<Summary>(`/cashflow/summary?month=${month}${personQuery(person)}`),
  sankey: (month: string, person: number | null) =>
    api<Sankey>(`/cashflow/sankey?month=${month}${personQuery(person)}`),
  series: (from: string, to: string, person: number | null) =>
    api<SeriesPoint[]>(`/cashflow/series?from=${from}&to=${to}${personQuery(person)}`),
  audit: () => api<AuditEntry[]>('/audit?limit=30'),
  createItem: (json: {
    name: string
    category_id?: number
    person_id?: number
    transfer_to_id?: number
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
