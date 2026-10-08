import { useEffect, useRef } from 'react'

import { useMonth } from '../month'
import { addMonths, MONTH_NAMES, monthRange } from '../monthUtils'

const YEARS_BACK = 3
const MONTHS_AHEAD = 60

/**
 * The tide gauge: a ruler of months. Past months are solid (measured, locked),
 * future months are hatched (planned, editable). The current month sits at the boundary.
 */
export function Pegel() {
  const { current, selected, setSelected } = useMonth()
  const months = monthRange(addMonths(current, -YEARS_BACK * 12), addMonths(current, MONTHS_AHEAD))
  const selectedRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    selectedRef.current?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [selected])

  return (
    <div
      role="group"
      aria-label="Monatsauswahl"
      className="overflow-x-auto border-y border-tinte/20 bg-karte-tief"
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') setSelected(addMonths(selected, -1))
        if (e.key === 'ArrowRight') setSelected(addMonths(selected, 1))
      }}
    >
      <div className="flex min-w-max items-stretch px-4">
        {months.map((m) => {
          const [y, mm] = m.split('-').map(Number)
          const locked = m < current
          const isCurrent = m === current
          const isSelected = m === selected
          return (
            <div key={m} className="flex flex-col">
              <span className="h-5 pl-1 text-[11px] leading-5 text-tinte-weich">{mm === 1 ? y : ''}</span>
              <button
                ref={isSelected ? selectedRef : undefined}
                type="button"
                aria-pressed={isSelected}
                aria-label={`${MONTH_NAMES[mm - 1]} ${y}${locked ? ', abgeschlossen' : ''}`}
                onClick={() => setSelected(m)}
                className={[
                  'relative h-9 w-11 border-l text-xs transition-colors',
                  mm === 1 ? 'border-tinte/50' : 'border-tinte/15',
                  isSelected
                    ? 'bg-tinte font-semibold text-karte'
                    : locked
                      ? 'bg-tinte/12 text-tinte-weich'
                      : 'text-tinte hover:bg-elbe/15',
                ].join(' ')}
                style={
                  !locked && !isSelected
                    ? {
                        backgroundImage:
                          'repeating-linear-gradient(135deg, transparent 0 5px, color-mix(in srgb, var(--color-tinte) 9%, transparent) 5px 6px)',
                      }
                    : undefined
                }
              >
                {MONTH_NAMES[mm - 1]}
                {isCurrent && (
                  <span aria-hidden className="absolute inset-x-0 bottom-0 h-[3px] bg-bake" />
                )}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
