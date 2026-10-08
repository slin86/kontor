import { useMemo } from 'react'

import { EChart } from '../charts/EChart'
import { euro } from '../format'
import type { Wealth } from '../wealthApi'
import { SERIES_COLORS } from './DepotChart'

const RED = '#d2432f'
const INK = '#12263a'

/**
 * Stacked areas: what you own above the zero line, what you owe below it. The dark line is the
 * net worth, the difference of both.
 */
export function WealthChart({ data, afterTax }: { data: Wealth; afterTax: boolean }) {
  const option = useMemo(() => {
    const depotIdx = data.series.findIndex((s) => s.group === 'depot')
    const taxAt = (i: number) => data.points[i].net - data.points[i].net_after_tax
    const labels = data.points.map((p) => (p.month.endsWith('-01') ? p.month.slice(0, 4) : ''))
    let owned = 0
    let owed = 0
    const areas = data.series.map((s, idx) => {
      const isDebt = s.group === 'debt'
      const color = isDebt ? RED : SERIES_COLORS[owned++ % SERIES_COLORS.length]
      const opacity = isDebt ? Math.max(0.3, 0.7 - 0.15 * owed++) : 0.85
      return {
        name: s.name,
        type: 'line',
        stack: isDebt ? 'debt' : 'asset',
        symbol: 'none',
        lineStyle: { width: 0 },
        itemStyle: { color },
        areaStyle: { color, opacity },
        emphasis: { focus: 'series' },
        data: data.points.map((p, i) => {
          const v = idx === depotIdx && afterTax ? p.values[idx] - taxAt(i) : p.values[idx]
          return isDebt ? -v : v
        }),
      }
    })
    const todayIdx = data.points.findIndex((p) => p.month === data.today)
    return {
      grid: { left: 64, right: 16, top: 40, bottom: 28 },
      legend: { top: 0, left: 0, type: 'scroll', icon: 'rect', itemWidth: 12, itemHeight: 10, textStyle: { color: '#4b5d6e' } },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v: number) => euro(Math.abs(v)),
        formatter: (items: { dataIndex: number; marker: string; seriesName: string; value: number }[]) => {
          const p = data.points[items[0].dataIndex]
          const net = afterTax ? p.net_after_tax : p.net
          const rows = items
            .filter((it) => it.seriesName !== 'Nettovermögen' && it.value !== 0)
            .map((it) => `${it.marker} ${it.seriesName}: ${euro(Math.abs(it.value))}${it.value < 0 ? ' Schuld' : ''}`)
          return [`<b>${p.month.slice(5)}/${p.month.slice(0, 4)}</b>`, ...rows, `<b>Nettovermögen: ${euro(net)}</b>`].join('<br/>')
        },
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: labels,
        axisLine: { lineStyle: { color: `${INK}55` } },
        axisLabel: { color: '#4b5d6e', interval: 0 },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) },
        splitLine: { lineStyle: { color: `${INK}1a` } },
      },
      series: [
        ...areas,
        {
          name: 'Nettovermögen',
          type: 'line',
          symbol: 'none',
          z: 10,
          data: data.points.map((p) => (afterTax ? p.net_after_tax : p.net)),
          lineStyle: { color: INK, width: 3 },
          itemStyle: { color: INK },
          markLine:
            todayIdx >= 0
              ? {
                  symbol: 'none',
                  silent: true,
                  label: { formatter: 'heute', color: '#4b5d6e' },
                  lineStyle: { color: '#4b5d6e', type: 'dashed' },
                  data: [{ xAxis: todayIdx }],
                }
              : undefined,
        },
      ],
    }
  }, [data, afterTax])
  return <EChart option={option} height={420} label="Entwicklung von Vermögen und Schulden mit dem Nettovermögen als Linie" />
}
