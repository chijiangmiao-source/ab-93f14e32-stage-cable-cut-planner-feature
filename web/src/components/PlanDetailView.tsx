import { Link } from 'react-router-dom'
import type { PlanOut, SegmentOut } from '../types'
import RollBar from './RollBar'

interface Props {
  plan: PlanOut
  /** True while a complete/undo request is in flight; locks every action. */
  busy: boolean
  onComplete: (rollPosition: number, cutPosition: number) => void
  onUndo: (rollPosition: number, cutPosition: number) => void
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

/** Every segment shows delivery, allowance and actual cut length, so a
 * zero (or unset) allowance is stated explicitly instead of hiding the
 * cut length behind a single number. */
function formatSegment(seg: SegmentOut): string {
  return (
    `${seg.id}（交付 ${seg.length} mm + 余量 ${seg.allowance} mm = ` +
    `下料 ${seg.length + seg.allowance} mm）`
  )
}

function SegmentStatus({
  rollPosition,
  index,
  segment,
  state,
}: {
  rollPosition: number
  index: number
  segment: SegmentOut
  state: 'done' | 'next' | 'pending'
}) {
  return (
    <li
      data-testid={`cut-${rollPosition}-${index + 1}`}
      className={`cut-status cut-status-${state}`}
      aria-current={state === 'next' ? 'true' : undefined}
    >
      <span className="cut-status-label">
        第 {index + 1} 段 {formatSegment(segment)}
      </span>
      {state === 'done' && (
        <span className="cut-status-meta">
          ✓ 已裁切 {formatTime(segment.completed_at as string)}
        </span>
      )}
      {state === 'next' && <span className="cut-status-meta">▶ 下一切</span>}
      {state === 'pending' && <span className="cut-status-meta">待切</span>}
    </li>
  )
}

/** Read-only rendering of a persisted plan plus live cutting progress.
 *  Every roll shows the full arithmetic so the foreman can recompute it by
 *  hand; action buttons are enabled solely from the server-provided state. */
export default function PlanDetailView({ plan, busy, onComplete, onUndo }: Props) {
  const totalSegments = plan.rolls.reduce(
    (acc, roll) => acc + roll.segments.length,
    0,
  )
  const allDone = plan.completed_segment_count === totalSegments

  return (
    <div className="plan-detail">
      <p className="detail-actions">
        <Link
          className="button-link"
          to={`/?from=${plan.id}`}
          data-testid="adjust-from-plan"
        >
          基于此方案调整
        </Link>
        {plan.source_plan_id !== null && plan.source_plan_id !== undefined && (
          <span className="source-line" data-testid="source-line">
            源自方案
            <Link to={`/plans/${plan.source_plan_id}`}>
              #{plan.source_plan_id}
            </Link>
          </span>
        )}
      </p>
      <dl className="summary">
        <div>
          <dt>卷长</dt>
          <dd>{plan.roll_length} mm</dd>
        </div>
        <div>
          <dt>锯口宽度</dt>
          <dd>{plan.kerf_width} mm</dd>
        </div>
        <div>
          <dt>线卷数</dt>
          <dd>{plan.rolls_used}</dd>
        </div>
        <div>
          <dt>总锯口</dt>
          <dd>{plan.total_kerf_count} 次</dd>
        </div>
        <div>
          <dt>总余料</dt>
          <dd>{plan.total_leftover} mm</dd>
        </div>
        <div>
          <dt>裁切进度</dt>
          <dd data-testid="overall-progress">
            {plan.completed_segment_count} / {totalSegments} 段
            {allDone && '（全部完成）'}
          </dd>
        </div>
        <div>
          <dt>创建时间</dt>
          <dd>{new Date(plan.created_at).toLocaleString()}</dd>
        </div>
      </dl>

      <h3>逐卷裁切方案</h3>
      {plan.rolls.map((roll) => {
        const lengthSum = roll.segments.reduce((acc, s) => acc + s.length, 0)
        const allowanceSum = roll.segments.reduce((acc, s) => acc + s.allowance, 0)
        const cutSum = lengthSum + allowanceSum
        const total = roll.segments.length
        const done = roll.completed_count
        const nextPosition = done < total ? done + 1 : null
        const nextSegment =
          nextPosition !== null ? roll.segments[nextPosition - 1] : null
        const lastSegment = done > 0 ? roll.segments[done - 1] : null
        const rollDone = nextPosition === null

        return (
          <section key={roll.position} className="roll-card">
            <h4>
              第 {roll.position} 卷
              <span
                className="roll-progress-badge"
                data-testid={`roll-progress-${roll.position}`}
              >
                已完成 {done} / {total} 段
              </span>
            </h4>
            <RollBar
              roll={roll}
              rollLength={plan.roll_length}
              kerfWidth={plan.kerf_width}
            />
            <p className="cutting-order">
              裁切顺序：
              {roll.segments.map(formatSegment).join(' → ')}
            </p>
            <p className="roll-math">
              {allowanceSum > 0 ? (
                <>
                  {cutSum}（下料合计 = 交付 {lengthSum} mm + 余量 {allowanceSum}{' '}
                  mm）+ {roll.kerf_count} × {plan.kerf_width}（锯口）= {roll.used_length}{' '}
                  mm ≤ {plan.roll_length} mm；余料 {roll.leftover} mm；锯口{' '}
                  {roll.kerf_count} 次
                </>
              ) : (
                <>
                  {lengthSum}（线长合计）+ {roll.kerf_count} × {plan.kerf_width}
                  （锯口）= {roll.used_length} mm ≤ {plan.roll_length} mm；余料{' '}
                  {roll.leftover} mm；锯口 {roll.kerf_count} 次
                </>
              )}
            </p>

            <ul className="cut-status-list" aria-label={`第 ${roll.position} 卷裁切进度`}>
              {roll.segments.map((segment, i) => (
                <SegmentStatus
                  key={segment.id}
                  rollPosition={roll.position}
                  index={i}
                  segment={segment}
                  state={
                    i < done ? 'done' : i === done && !rollDone ? 'next' : 'pending'
                  }
                />
              ))}
            </ul>

            <div className="cut-actions">
              <button
                type="button"
                data-testid={`complete-roll-${roll.position}`}
                disabled={busy || rollDone}
                onClick={() => onComplete(roll.position, nextPosition as number)}
              >
                {rollDone
                  ? '本卷已全部完成'
                  : `完成此段（第 ${nextPosition} 段：${nextSegment?.id}）`}
              </button>
              <button
                type="button"
                className="secondary-btn"
                data-testid={`undo-roll-${roll.position}`}
                disabled={busy || done === 0}
                onClick={() => onUndo(roll.position, done)}
              >
                {done === 0
                  ? '无可撤销段'
                  : `撤销末段（第 ${done} 段：${lastSegment?.id}）`}
              </button>
            </div>
          </section>
        )
      })}
    </div>
  )
}
