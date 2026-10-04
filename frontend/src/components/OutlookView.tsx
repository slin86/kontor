import { useMemo } from 'react'

import { EChart } from '../charts/EChart'
import { euro } from '../format'
import type { Outlook } from '../financingApi'
import { MONTH_NAMES } from '../monthUtils'

function short(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return `${MONTH_NAMES[m - 1]} ${String(y).slice(2)}`
}

/** Costs as stacked areas, income as a dashed line, and the free budget as the emphasised line. */
export function OutlookView({ data }: { data: Outlook }) {
  const option = useMemo(() => {
    const labels = data.points.map((p) => short(p.month))
    const marks = data.events.map((e) => ({ xAxis: short(e.month) }))
    return {
      grid: { left: 64, right: 16, top: 36, bottom: 28 },
      legend: { top: 0, left: 0, textStyle: { color: '#4b5d6e' } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => euro(v) },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#12263a55' } },
        axisLabel: { color: '#4b5d6e', interval: 23 },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) },
        splitLine: { lineStyle: { color: '#12263a1a' } },
      },
      series: [
        {
          name: 'Ausgaben',
          type: 'line',
          stack: 'costs',
          symbol: 'none',
          step: 'end',
          areaStyle: { color: '#b9a572', opacity: 0.55 },
          lineStyle: { width: 0 },
          itemStyle: { color: '#b9a572' },
          data: data.points.map((p) => p.expenses),
        },
        {
          name: 'Finanzierungen',
          type: 'line',
          stack: 'costs',
          symbol: 'none',
          step: 'end',
          areaStyle: { color: '#6d8aa0', opacity: 0.6 },
          lineStyle: { width: 0 },
          itemStyle: { color: '#6d8aa0' },
          data: data.points.map((p) => p.financing),
        },
        {
          name: 'Einnahmen',
          type: 'line',
          symbol: 'none',
          step: 'end',
          lineStyle: { color: '#2e7c86', width: 1.5, type: 'dashed' },
          itemStyle: { color: '#2e7c86' },
          data: data.points.map((p) => p.income),
        },
        {
          name: 'Frei verfügbar',
          type: 'line',
          symbol: 'none',
          step: 'end',
          lineStyle: { color: '#12263a', width: 3 },
          itemStyle: { color: '#12263a' },
          data: data.points.map((p) => p.free),
          markLine: {
            silent: true,
            symbol: 'none',
            label: { show: false },
            lineStyle: { color: '#12263a', opacity: 0.35, type: 'dotted' },
            data: marks,
          },
        },
      ],
    }
  }, [data])
  return <EChart option={option} height={340} label="Entwicklung des frei verfügbaren Monatsbudgets" />
}
