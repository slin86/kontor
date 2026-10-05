import { useMemo } from 'react'

import { EChart } from '../charts/EChart'
import type { Comparison } from '../actualsApi'
import { euro } from '../format'
import { MONTH_NAMES } from '../monthUtils'

function short(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return `${MONTH_NAMES[m - 1]} ${String(y).slice(2)}`
}

/** Planned against real values for the positions that have month-end values. */
export function ValueChart({ data }: { data: Comparison }) {
  const option = useMemo(() => {
    const labels = data.points.map((p) => short(p.month))
    const hasActual = data.points.some((p) => p.actual !== null)
    return {
      grid: { left: 72, right: 16, top: 40, bottom: 28 },
      legend: { top: 0, left: 0, textStyle: { color: '#4b5d6e' } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number | null) => (v === null ? 'kein Wert' : euro(v)) },
      xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: '#12263a55' } }, axisLabel: { color: '#4b5d6e', hideOverlap: true } },
      yAxis: { type: 'value', axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) }, splitLine: { lineStyle: { color: '#12263a1a' } } },
      series: [
        {
          name: hasActual ? 'Plan (Positionen mit Ist-Wert)' : 'Plan',
          type: 'line',
          symbol: 'none',
          lineStyle: { color: '#6d8aa0', width: 2, type: 'dashed' },
          itemStyle: { color: '#6d8aa0' },
          data: data.points.map((p) => (hasActual ? p.planned_tracked : p.planned_total)),
        },
        ...(hasActual
          ? [
              {
                name: 'Ist',
                type: 'line',
                connectNulls: true,
                symbolSize: 8,
                lineStyle: { color: '#1f5c64', width: 3 },
                itemStyle: { color: '#1f5c64' },
                data: data.points.map((p) => p.actual),
              },
            ]
          : []),
      ],
    }
  }, [data])
  return <EChart option={option} height={340} label="Plan und Ist des Depotwerts" />
}

/** Net deposits per month: plan against real buys minus sells. */
export function DepositChart({ data }: { data: Comparison }) {
  const option = useMemo(() => {
    const labels = data.points.map((p) => short(p.month))
    return {
      grid: { left: 64, right: 16, top: 40, bottom: 28 },
      legend: { top: 0, left: 0, textStyle: { color: '#4b5d6e' } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => euro(v) },
      xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: '#12263a55' } }, axisLabel: { color: '#4b5d6e', hideOverlap: true } },
      yAxis: { type: 'value', axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) }, splitLine: { lineStyle: { color: '#12263a1a' } } },
      series: [
        { name: 'Plan', type: 'bar', itemStyle: { color: '#6d8aa0' }, data: data.points.map((p) => p.planned_deposit) },
        { name: 'Ist', type: 'bar', itemStyle: { color: '#1f5c64' }, data: data.points.map((p) => p.actual_deposit) },
      ],
    }
  }, [data])
  return <EChart option={option} height={260} label="Geplante und tatsächliche Einzahlungen pro Monat" />
}
