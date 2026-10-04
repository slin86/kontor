import { useMemo } from 'react'

import { EChart } from '../charts/EChart'
import type { SeriesPoint } from '../cashflowApi'
import { euro } from '../format'
import { MONTH_NAMES } from '../monthUtils'

function short(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return `${MONTH_NAMES[m - 1]} ${String(y).slice(2)}`
}

export function SeriesView({ data }: { data: SeriesPoint[] }) {
  const option = useMemo(
    () => ({
      grid: { left: 56, right: 16, top: 32, bottom: 28 },
      legend: { top: 0, left: 0, textStyle: { color: '#4b5d6e' } },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v: number) => euro(v),
      },
      xAxis: {
        type: 'category',
        data: data.map((p) => short(p.month)),
        axisLine: { lineStyle: { color: '#12263a55' } },
        axisLabel: { color: '#4b5d6e', interval: 'auto' },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) },
        splitLine: { lineStyle: { color: '#12263a1a' } },
      },
      series: [
        { name: 'Einnahmen', type: 'bar', data: data.map((p) => p.income), itemStyle: { color: '#2e7c86' }, barGap: '10%' },
        { name: 'Ausgaben', type: 'bar', data: data.map((p) => p.expenses), itemStyle: { color: '#b9a572' } },
        {
          name: 'Übrig',
          type: 'line',
          data: data.map((p) => p.balance),
          symbol: 'none',
          lineStyle: { color: '#12263a', width: 2 },
          itemStyle: { color: '#12263a' },
        },
      ],
    }),
    [data],
  )
  return <EChart option={option} height={300} label="Einnahmen, Ausgaben und Überschuss je Monat" />
}
