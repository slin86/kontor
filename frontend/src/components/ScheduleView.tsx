import { useMemo } from 'react'

import { EChart } from '../charts/EChart'
import { euro } from '../format'
import type { ScheduleRow } from '../financingApi'

/** Yearly interest, repayment and savings as stacked bars, with the balance at year end. */
export function ScheduleView({ rows }: { rows: ScheduleRow[] }) {
  const option = useMemo(() => {
    const years = new Map<string, { interest: number; principal: number; saving: number; balance: number }>()
    for (const r of rows) {
      const y = r.month.slice(0, 4)
      const acc = years.get(y) ?? { interest: 0, principal: 0, saving: 0, balance: 0 }
      acc.interest += r.interest
      acc.principal += r.principal
      acc.saving += r.saving + r.fee
      acc.balance = r.balance
      years.set(y, acc)
    }
    const labels = [...years.keys()]
    const values = [...years.values()]
    const bar = (name: string, key: 'interest' | 'principal' | 'saving', color: string) => ({
      name,
      type: 'bar',
      stack: 'year',
      itemStyle: { color },
      data: values.map((v) => Math.round(v[key] * 100) / 100),
    })
    return {
      grid: { left: 64, right: 64, top: 36, bottom: 28 },
      legend: { top: 0, left: 0, textStyle: { color: '#4b5d6e' } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => euro(v) },
      xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: '#12263a55' } }, axisLabel: { color: '#4b5d6e' } },
      yAxis: [
        {
          type: 'value',
          axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) },
          splitLine: { lineStyle: { color: '#12263a1a' } },
        },
        { type: 'value', axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) }, splitLine: { show: false } },
      ],
      series: [
        bar('Zinsen', 'interest', '#d2432f'),
        bar('Tilgung', 'principal', '#2e7c86'),
        bar('Sparen und Gebühren', 'saving', '#b9a572'),
        {
          name: 'Stand am Jahresende',
          type: 'line',
          yAxisIndex: 1,
          symbol: 'none',
          lineStyle: { color: '#12263a', width: 2.5 },
          itemStyle: { color: '#12263a' },
          data: values.map((v) => v.balance),
        },
      ],
    }
  }, [rows])
  return <EChart option={option} height={320} label="Zinsen, Tilgung und Restbetrag je Jahr" />
}
