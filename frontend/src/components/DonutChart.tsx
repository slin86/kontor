import { useMemo } from 'react'

import { EChart } from '../charts/EChart'
import { euro, percent } from '../format'
import { SERIES_COLORS } from './DepotChart'

export interface Slice {
  name: string
  value: number
}

/** Donut with a headline figure in the middle. */
export function DonutChart({ slices, center, caption, height = 260 }: { slices: Slice[]; center: string; caption: string; height?: number }) {
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
        top: '40%',
        textStyle: { color: '#12263a', fontSize: 20, fontWeight: 600 },
        subtextStyle: { color: '#4b5d6e', fontSize: 12 },
      },
      series: [
        {
          type: 'pie',
          radius: ['52%', '78%'],
          center: ['50%', '50%'],
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
  // The legend is plain HTML below the chart: with many slices an in-chart legend wraps onto several
  // rows and runs into the ring.
  return (
    <div>
      <EChart option={option} height={height} label={`${caption}: Anteile als Kuchendiagramm`} />
      <ul className="mt-3 space-y-1 text-sm text-tinte-weich">
        {slices.map((slice, i) => (
          <li key={slice.name} className="flex items-center gap-2">
            <span aria-hidden className="size-2.5 shrink-0 rounded-sm" style={{ background: SERIES_COLORS[i % SERIES_COLORS.length] }} />
            <span className="min-w-0 flex-1 truncate">{slice.name}</span>
            <span className="tabular-nums">{euro(slice.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
