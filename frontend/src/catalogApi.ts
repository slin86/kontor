import { api } from './api'
import type { InstrumentKind } from './depotApi'

export interface CatalogEntry {
  id: number
  kind: InstrumentKind
  isin: string | null
  name: string
  index_name: string | null
  ter_percent: number
  distribution: string | null
  replication: string | null
  domicile: string | null
  fund_size_m_eur: number | null
  builtin: boolean
  source: string | null
  as_of: string | null
}

export interface SearchResult {
  total: number
  items: CatalogEntry[]
  facets: { indexes: string[]; distributions: string[]; replications: string[] }
}

export interface CostResult {
  entry: CatalogEntry
  final_value: number
  total_costs: number
  extra_vs_cheapest: number
}

export interface Comparison {
  monthly: number
  years: number
  expected_return_percent: number
  start_value: number
  paid_in: number
  results: CostResult[]
}

export interface SearchParams {
  q: string
  index: string
  distribution: string
  replication: string
  maxTer: string
  sort: 'size' | 'ter' | 'name'
  kind: string
}

export interface NewEntry {
  kind: InstrumentKind
  name: string
  isin: string | null
  index_name: string | null
  ter_percent: string
  distribution: string | null
}

export const DISTRIBUTION_LABEL: Record<string, string> = {
  accumulating: 'Thesaurierend',
  distributing: 'Ausschüttend',
}

export const REPLICATION_LABEL: Record<string, string> = {
  full_replication: 'Vollständige Replikation',
  optimized_sampling: 'Optimiertes Sampling',
  swap: 'Swap',
  mixed: 'Physisch und synthetisch',
}

export const catalogApi = {
  search: (p: SearchParams, limit = 100) => {
    const query = new URLSearchParams({ sort: p.sort, limit: String(limit) })
    if (p.q.trim()) query.set('q', p.q.trim())
    if (p.index) query.set('index', p.index)
    if (p.distribution) query.set('distribution', p.distribution)
    if (p.replication) query.set('replication', p.replication)
    if (p.kind) query.set('kind', p.kind)
    if (p.maxTer) query.set('max_ter', p.maxTer)
    return api<SearchResult>(`/catalog?${query}`)
  },
  compare: (ids: number[], monthly: number, years: number, expectedReturn: number) =>
    api<Comparison>(
      `/catalog/compare?ids=${ids.join(',')}&monthly=${monthly}&years=${years}&expected_return=${expectedReturn}`,
    ),
  create: (json: NewEntry) => api<CatalogEntry>('/catalog', { method: 'POST', json }),
  remove: (id: number) => api<void>(`/catalog/${id}`, { method: 'DELETE' }),
}
