import type { ReactElement } from 'react'
import type { RollOut } from '../types'

interface Props {
  roll: RollOut
  rollLength: number
  kerfWidth: number
}

/** Proportional bar: segments (sized by their cut length, i.e. delivered
 *  length + allowance), kerf gaps between them, leftover at the tail. */
export default function RollBar({ roll, rollLength, kerfWidth }: Props) {
  const parts: ReactElement[] = []
  roll.segments.forEach((seg, i) => {
    const cut = seg.length + seg.allowance
    const isDone = seg.completed_at != null
    const isNext = !isDone && i === roll.completed_count
    const stateClass = isDone
      ? 'rollbar-segment is-done'
      : isNext
        ? 'rollbar-segment is-next'
        : 'rollbar-segment'
    const measurement = `${seg.id}: 交付 ${seg.length} mm + 余量 ${seg.allowance} mm = 下料 ${cut} mm`
    const title = isDone
      ? `${measurement}（已裁切 ${new Date(seg.completed_at as string).toLocaleString()}）`
      : isNext
        ? `${measurement}（下一段待切）`
        : measurement
    parts.push(
      <div
        key={`seg-${seg.id}`}
        className={stateClass}
        style={{ width: `${(cut / rollLength) * 100}%` }}
        title={title}
      >
        {isDone ? `✓ ${seg.id}` : seg.id}
      </div>,
    )
    if (i < roll.segments.length - 1) {
      parts.push(
        <div
          key={`kerf-${i}`}
          className="rollbar-kerf"
          style={{ width: `${(kerfWidth / rollLength) * 100}%` }}
          title={`锯口 ${kerfWidth} mm`}
        />,
      )
    }
  })
  if (roll.leftover > 0) {
    parts.push(
      <div
        key="leftover"
        className="rollbar-leftover"
        style={{ width: `${(roll.leftover / rollLength) * 100}%` }}
        title={`余料 ${roll.leftover} mm`}
      />,
    )
  }
  return <div className="rollbar">{parts}</div>
}
