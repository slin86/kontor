import { useMemo } from 'react'

import { EChart } from '../charts/EChart'
import { euro, percent } from '../format'
import { SERIES_COLORS } from './DepotChart'

export interface Slice {
  name: string
  value: number
}

/** Donut with a headline figure in the middle. */
export function DonutChart({ slices, center, caption, height = 300 }: { slices: Slice[]; center: string; caption: string; height?: number }) {
  const option = useMemo(
    () => ({
      color: SERIES_COLORS,
      tooltip: {
        trigger: 'item',
        formatter: (p: { name: string; value: number; percent: number }) => `${p.name}: ${euro(p.value)} · ${percent(p.percent / 100)}`,
      },
      title: {
        text: center,
        subtext: caption,
        left: 'center',
        top: '34%',
        textStyle: { color: '#12263a', fontSize: 20, fontWeight: 600 },
        subtextStyle: { color: '#4b5d6e', fontSize: 12 },
      },
      legend: { bottom: 0, icon: 'rect', itemWidth: 10, itemHeight: 10, textStyle: { color: '#4b5d6e' } },
      series: [
        {
          type: 'pie',
          radius: ['52%', '78%'],
          center: ['50%', '42%'],
          label: { show: false },
          itemStyle: { borderColor: 'transparent', borderWidth: 2 },
          emphasis: { scale: true, scaleSize: 4 },
          data: slices,
        },
      ],
    }),
    [slices, center, caption],
  )
  if (slices.length === 0) return null
  return <EChart option={option} height={height} label={`${caption}: Anteile als Kuchendiagramm`} />
}
