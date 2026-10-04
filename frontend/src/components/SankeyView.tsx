import { useMemo } from 'react'

import { EChart } from '../charts/EChart'
import type { Sankey } from '../cashflowApi'
import { euro } from '../format'

const COLORS = {
  income: '#2e7c86',
  hub: '#12263a',
  expense: '#b9a572',
  surplus: '#2e7c86',
  deficit: '#d2432f',
}

export function SankeyView({ data }: { data: Sankey }) {
  const option = useMemo(() => {
    const names = Object.fromEntries(data.nodes.map((n) => [n.id, n.name]))
    return {
      tooltip: {
        trigger: 'item',
        formatter: (p: { dataType: string; data: { source?: string; target?: string; value: number; name?: string } }) =>
          p.dataType === 'edge'
            ? `${names[p.data.source ?? '']} → ${names[p.data.target ?? '']}: ${euro(p.data.value)}`
            : `${names[p.data.name ?? '']}: ${euro(p.data.value)}`,
      },
      series: [
        {
          type: 'sankey',
          left: 8,
          right: 190,
          top: 8,
          bottom: 8,
          nodeWidth: 14,
          nodeGap: 10,
          draggable: false,
          emphasis: { focus: 'adjacency' },
          lineStyle: { color: 'gradient', opacity: 0.35, curveness: 0.5 },
          label: {
            color: '#12263a',
            fontFamily: 'Hanken Grotesk Variable, system-ui, sans-serif',
            fontSize: 13,
            formatter: (p: { name: string; value: number }) => `${names[p.name]}  ${euro(p.value)}`,
          },
          data: data.nodes.map((n) => ({ name: n.id, itemStyle: { color: COLORS[n.kind] } })),
          links: data.links,
        },
      ],
    }
  }, [data])

  const height = Math.max(280, 60 + data.nodes.length * 26)
  return <EChart option={option} height={height} label="Sankey-Diagramm der monatlichen Geldflüsse" />
}
