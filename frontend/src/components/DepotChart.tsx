import { useMemo } from 'react'

import { EChart } from '../charts/EChart'
import { euro } from '../format'
import type { Projection } from '../depotApi'
import { MONTH_NAMES } from '../monthUtils'

export const SERIES_COLORS = ['#2e7c86', '#b9a572', '#6d8aa0', '#8d6a9f', '#c07a4a', '#5e8f5a']

function short(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return `${MONTH_NAMES[m - 1]} ${String(y).slice(2)}`
}

/**
 * Expected development as stacked areas per position, deposits as a dashed line. The vertical line marks today: everything left of it is history.
 */
export function DepotChart({
  base,
  today,
}: {
  base: Projection
  today: string
}) {
  const option = useMemo(() => {
    const narrow = typeof window !== 'undefined' && window.innerWidth < 640
    const labels = base.points.map((p) => short(p.month))
    const todayLabel = short(today)
    const positions = base.instruments.map((ins, n) => ({
      name: ins.name,
      type: 'line',
      stack: 'value',
      symbol: 'none',
      areaStyle: { color: SERIES_COLORS[n % SERIES_COLORS.length], opacity: 0.55 },
      lineStyle: { width: 0 },
      itemStyle: { color: SERIES_COLORS[n % SERIES_COLORS.length] },
      data: base.points.map((p) => p.balances[n]),
      ...(n === 0 ? { markLine: { symbol: 'none', silent: true, label: { formatter: 'Heute', color: '#12263a' }, lineStyle: { color: '#12263a', type: 'solid', width: 1 }, data: [{ xAxis: todayLabel }] } } : {}),
    }))
    const line = (name: string, data: number[], color: string, type: 'dashed' | 'solid', width: number) => ({
      name,
      type: 'line',
      symbol: 'none',
      lineStyle: { color, type, width },
      itemStyle: { color },
      data,
    })
    const series: object[] = [
      ...positions,
      line('Eingezahlt', base.points.map((p) => p.paid_in), '#12263a', 'dashed', 2),
      line('Nach Steuern bei Verkauf', base.points.map((p) => p.net_value), '#c07a4a', 'solid', 2),
    ]
    return {
      grid: { left: 72, right: 16, top: narrow ? 84 : 40, bottom: 28 },
      legend: { top: 0, left: 0, textStyle: { color: '#4b5d6e' } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => euro(v) },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#12263a55' } },
        axisTick: { show: false },
        axisLabel: {
          color: '#4b5d6e',
          interval: 0,
          hideOverlap: true,
          // one label per January, showing just the year
          formatter: (v: string) => (v.startsWith('Jan') ? `20${v.slice(4)}` : ''),
        },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) },
        splitLine: { lineStyle: { color: '#12263a1a' } },
      },
      series,
    }
  }, [base, today])

  return <EChart option={option} height={420} label="Prognose des Depotwerts" />
}
