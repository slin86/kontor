import { useQuery } from '@tanstack/react-query'

import { cashflowApi } from '../../cashflowApi'
import { useMonth } from '../../month'
import { addMonths } from '../../monthUtils'
import { usePerson } from '../../person'

/** The queries all three cashflow views share (react-query de-duplicates them). */
export function useCashflowData() {
  const { selected } = useMonth()
  const { selectedId } = usePerson()
  const from = addMonths(selected, -6)
  const to = addMonths(selected, 17)
  return {
    items: useQuery({ queryKey: ['cashflow', 'items', selected, selectedId], queryFn: () => cashflowApi.items(selected, selectedId) }),
    summary: useQuery({ queryKey: ['cashflow', 'summary', selected, selectedId], queryFn: () => cashflowApi.summary(selected, selectedId) }),
    sankey: useQuery({ queryKey: ['cashflow', 'sankey', selected, selectedId], queryFn: () => cashflowApi.sankey(selected, selectedId) }),
    series: useQuery({ queryKey: ['cashflow', 'series', from, to, selectedId], queryFn: () => cashflowApi.series(from, to, selectedId) }),
  }
}
