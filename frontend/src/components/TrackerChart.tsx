import { useMemo } from 'react'

import { EChart } from '../charts/EChart'
import type { Overview } from '../actualsApi'
import { euro } from '../format'
import { MONTH_NAMES } from '../monthUtils'

function short(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return `${MONTH_NAMES[m - 1]} ${String(y).slice(2)}`
}

/** Real history, forecast from the latest real value, and the plan as a reference line. */
export function TrackerChart({ data }: { data: Overview }) {
  const option = useMemo(() => {
    const labels = data.points.map((p) => short(p.month))
    const hasActual = data.points.some((p) => p.actual !== null)
    return {
      grid: { left: 72, right: 16, top: 40, bottom: 28 },
      legend: { top: 0, left: 0, textStyle: { color: '#4b5d6e' } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number | null) => (v === null || v === undefined ? '–' : euro(v)) },
      xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: '#12263a55' } }, axisLabel: { color: '#4b5d6e', hideOverlap: true } },
      yAxis: { type: 'value', axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) }, splitLine: { lineStyle: { color: '#12263a1a' } } },
      series: [
        {
          name: 'Plan',
          type: 'line',
          symbol: 'none',
          lineStyle: { color: '#6d8aa0', width: 2, type: 'dashed' },
          itemStyle: { color: '#6d8aa0' },
          data: data.points.map((p) => p.plan),
          markLine: {
            symbol: 'none',
            silent: true,
            label: { formatter: 'Heute', color: '#12263a' },
            lineStyle: { color: '#12263a', type: 'solid', width: 1 },
            data: [{ xAxis: short(data.today) }],
          },
        },
        ...(hasActual
          ? [
              {
                name: 'Ist',
                type: 'line',
                connectNulls: true,
                symbolSize: 6,
                lineStyle: { color: '#1f5c64', width: 3 },
                itemStyle: { color: '#1f5c64' },
                data: data.points.map((p) => p.actual),
              },
              {
                name: 'Prognose',
                type: 'line',
                symbol: 'none',
                lineStyle: { color: '#c07a4a', width: 3 },
                itemStyle: { color: '#c07a4a' },
                data: data.points.map((p) => p.forecast),
              },
            ]
          : []),
      ],
    }
  }, [data])
  return <EChart option={option} height={360} label="Depotwert: Ist, Prognose und Plan" />
}

/** How far the real values were from the plan, month by month. */
export function DeviationChart({ data }: { data: Overview }) {
  const option = useMemo(() => {
    const rows = data.points.filter((p) => p.actual !== null)
    return {
      grid: { left: 72, right: 16, top: 16, bottom: 28 },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${v > 0 ? '+' : ''}${euro(v)}` },
      xAxis: { type: 'category', data: rows.map((p) => short(p.month)), axisLine: { lineStyle: { color: '#12263a55' } }, axisLabel: { color: '#4b5d6e', hideOverlap: true } },
      yAxis: { type: 'value', axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) }, splitLine: { lineStyle: { color: '#12263a1a' } } },
      series: [
        {
          name: 'Abweichung vom Plan',
          type: 'bar',
          data: rows.map((p) => ({
            value: Math.round(((p.actual as number) - p.plan) * 100) / 100,
            itemStyle: { color: (p.actual as number) >= p.plan ? '#2e7c86' : '#d2432f' },
          })),
        },
      ],
    }
  }, [data])
  return <EChart option={option} height={200} label="Abweichung der echten Werte vom Plan" />
}
