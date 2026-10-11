import { useMemo, useState } from 'react'

import { EChart } from '../charts/EChart'
import type { Sankey } from '../cashflowApi'
import { euro } from '../format'

const COLORS = {
  income: '#2e7c86',
  hub: '#12263a',
  expense: '#b9a572',
  financing: '#6d8aa0',
  purpose: '#4f6b82',
  surplus: '#2e7c86',
  deficit: '#d2432f',
}

/**
 * The overview keeps what is easy to read: income, household, expense groups, financings and what
 * is left. Sub-categories and the single contracts of the financing branch are details.
 */
function overview(data: Sankey): Sankey {
  const children = new Set(data.links.filter((l) => l.source.startsWith('expense:')).map((l) => l.target))
  const contracts = new Set(data.nodes.map((n) => n.id).filter((id) => id.startsWith('financing:')))
  const drop = new Set([...children, ...contracts])
  const merged = new Map<string, { source: string; target: string; value: number }>()
  const add = (source: string, target: string, value: number) => {
    const key = `${source}>${target}`
    const prev = merged.get(key)
    if (prev) prev.value += value
    else merged.set(key, { source, target, value })
  }
  for (const l of data.links) {
    if (contracts.has(l.source) && !drop.has(l.target)) add('financing', l.target, l.value) // contract -> purpose
    else if (!drop.has(l.source) && !drop.has(l.target)) add(l.source, l.target, l.value)
  }
  return { ...data, nodes: data.nodes.filter((n) => !drop.has(n.id)), links: [...merged.values()] }
}

export function SankeyView({ data: full }: { data: Sankey }) {
  const [detail, setDetail] = useState(false)
  const data = useMemo(() => (detail ? full : overview(full)), [full, detail])
  const hasDetail = useMemo(() => overview(full).nodes.length < full.nodes.length, [full])

  const option = useMemo(() => {
    const names = Object.fromEntries(data.nodes.map((n) => [n.id, n.name]))
    return {
      tooltip: {
        trigger: 'item',
        // an edge carries its value in data, a node has it on the event itself
        formatter: (p: { dataType: string; name: string; value: number; data: { source?: string; target?: string; value?: number } }) =>
          p.dataType === 'edge'
            ? `${names[p.data.source ?? '']} → ${names[p.data.target ?? '']}: ${euro(p.data.value ?? 0)}`
            : `${names[p.name] ?? p.name}: ${euro(p.value ?? 0)}`,
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
          nodeAlign: 'left', // a node sits right after its source instead of being pushed to the last column
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

  const height = Math.max(280, 60 + data.nodes.length * 24)
  return (
    <div className="space-y-2">
      {hasDetail && (
        <div className="flex gap-4 text-sm font-medium" role="group" aria-label="Detailgrad">
          {(
            [
              [false, 'Übersicht'],
              [true, 'Mit Unterkategorien und Verträgen'],
            ] as const
          ).map(([value, label]) => (
            <button
              key={label}
              type="button"
              aria-pressed={detail === value}
              onClick={() => setDetail(value)}
              className={`border-b-2 pb-0.5 ${detail === value ? 'border-elbe' : 'border-transparent text-tinte-weich'}`}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      <EChart option={option} height={height} label="Sankey-Diagramm der monatlichen Geldflüsse" />
    </div>
  )
}
