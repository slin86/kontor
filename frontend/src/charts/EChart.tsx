import { BarChart, LineChart, SankeyChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import type { EChartsCoreOption } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useMemo, useRef } from 'react'

import { useTheme } from '../theme'

echarts.use([SankeyChart, BarChart, LineChart, TooltipComponent, GridComponent, LegendComponent, MarkLineComponent, CanvasRenderer])

// Charts are written with the light palette; in dark mode these colors are swapped on the fly.
const DARK_COLORS: Record<string, string> = {
  '#12263a': '#e3ebe8',
  '#4b5d6e': '#9fb2bd',
  '#2e7c86': '#4fb0bb',
  '#1f5c64': '#6cc3cc',
  '#4f6b82': '#7794ab',
  '#6d8aa0': '#8aa6bb',
  '#b9a572': '#c9b67f',
  '#d2432f': '#ef6a55',
  '#8d6a9f': '#b08bc4',
  '#c07a4a': '#d9955f',
  '#5e8f5a': '#7fb87a',
}

function recolor(value: unknown): unknown {
  if (typeof value === 'string') {
    const m = /^(#[0-9a-f]{6})([0-9a-f]{2})?$/i.exec(value)
    const mapped = m && DARK_COLORS[m[1].toLowerCase()]
    return mapped ? mapped + (m[2] ?? '') : value
  }
  if (Array.isArray(value)) return value.map(recolor)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, recolor(v)]))
  }
  return value
}

function darkOption(option: EChartsCoreOption): EChartsCoreOption {
  const tooltip = (option as { tooltip?: object }).tooltip
  return {
    ...(recolor(option) as object),
    tooltip: {
      ...(recolor(tooltip ?? {}) as object),
      backgroundColor: '#16283a',
      borderColor: '#2d4256',
      textStyle: { color: '#e3ebe8' },
    },
  }
}

/** Minimal ECharts wrapper: creates the chart once, updates options, resizes with its container. */
export function EChart({ option, height, label }: { option: EChartsCoreOption; height: number; label: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const instance = echarts.init(el)
    chart.current = instance
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(el)
    return () => {
      observer.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [])

  const { dark } = useTheme()
  const themed = useMemo(() => (dark ? darkOption(option) : option), [dark, option])
  useEffect(() => {
    chart.current?.setOption(themed, true)
  }, [themed])

  return <div ref={ref} role="img" aria-label={label} style={{ height, width: '100%' }} />
}
