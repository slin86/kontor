import { useMemo } from 'react'

import type { Group } from '../cashflowApi'
import { EChart } from '../charts/EChart'
import { euro, percent } from '../format'
import { SERIES_COLORS } from './DepotChart'

/** Donut chart of the expense groups; the total sits in the middle. */
export function ExpensePie({ groups, total, height = 300 }: { groups: Group[]; total: number; height?: number }) {
  const option = useMemo(
    () => ({
      color: SERIES_COLORS,
      tooltip: {
        trigger: 'item',
        formatter: (p: { name: string; value: number; percent: number }) => `${p.name}: ${euro(p.value)} · ${percent(p.percent / 100)}`,
      },
      title: {
        text: euro(total),
        subtext: 'Ausgaben',
        left: 'center',
        top: '34%',
        textStyle: { color: '#12263a', fontSize: 20, fontWeight: 600 },
        subtextStyle: { color: '#4b5d6e', fontSize: 12 },
      },
      series: [
        {
          type: 'pie',
          radius: ['52%', '78%'],
          center: ['50%', '42%'],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: 'transparent', borderWidth: 2 },
          label: { show: false },
          emphasis: { scale: true, scaleSize: 4 },
          data: groups.map((g) => ({ name: g.name, value: g.total })),
        },
      ],
      legend: { bottom: 0, icon: 'rect', itemWidth: 10, itemHeight: 10, textStyle: { color: '#4b5d6e' } },
    }),
    [groups, total],
  )
  if (groups.length === 0 || total <= 0) return null
  return <EChart option={option} height={height} label="Kuchendiagramm der Ausgaben nach Kategorie" />
}
