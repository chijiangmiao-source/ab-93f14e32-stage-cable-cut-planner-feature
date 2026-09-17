import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, createPlan } from '../api'
import { groupErrors } from '../errors'
import {
  MAX_ALLOWANCE,
  MAX_SEGMENTS,
  addRow,
  makeRow,
  removeRow,
  updateRow,
} from '../segmentRows'
import type { SegmentRow } from '../segmentRows'

export interface PlanFormInitial {
  roll_length: number
  kerf_width: number
  segments: { id: string; length: number; allowance?: number }[]
}

interface PlanFormProps {
  // When adjusting from an existing plan the roll length, kerf width and
  // segments are carried over verbatim; the form stays fully editable.
  initial?: PlanFormInitial
  sourcePlanId?: number | null
}

function FieldErrors({ messages }: { messages?: string[] }) {
  if (!messages || messages.length === 0) return null
  return (
    <span className="field-error" role="alert">
      {messages.join('；')}
    </span>
  )
}

export default function PlanForm({ initial, sourcePlanId = null }: PlanFormProps) {
  const navigate = useNavigate()
  const [rollLength, setRollLength] = useState(() =>
    initial ? String(initial.roll_length) : '1000',
  )
  const [kerfWidth, setKerfWidth] = useState(() =>
    initial ? String(initial.kerf_width) : '10',
  )
  const [rows, setRows] = useState<SegmentRow[]>(() =>
    initial
      ? initial.segments.map((s) =>
          makeRow(s.id, String(s.length), String(s.allowance ?? 0)),
        )
      : [
          makeRow('S1', '600'),
          makeRow('S2', '590'),
          makeRow('S3', '400'),
        ],
  )
  // Provenance only; the solver never sees anything besides the edited input.
  const [sourceId, setSourceId] = useState<number | null>(sourcePlanId)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [sourcePick, setSourcePick] = useState('')
  const [errors, setErrors] = useState<Map<string, string[]>>(new Map())
  const [topError, setTopError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const fieldError = (key: string) => errors.get(key)

  function confirmSourcePick() {
    const value = Number(sourcePick)
    if (!Number.isInteger(value) || value < 1) return
    // Re-selecting a source keeps every edit in place; the next submit
    // retries with the new provenance link.
    setSourceId(value)
    setSourceError(null)
    setSourcePick('')
    setErrors((prev) => {
      if (!prev.has('source_plan_id')) return prev
      const next = new Map(prev)
      next.delete('source_plan_id')
      return next
    })
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setTopError(null)
    setSourceError(null)
    setErrors(new Map())

    // Light client-side check; the API remains the authority and its 422
    // errors are mapped back onto the same field keys below.
    const local = new Map<string, string[]>()
    const push = (key: string, msg: string) =>
      local.set(key, [...(local.get(key) ?? []), msg])
    const parseLen = (raw: string, key: string): number => {
      const value = Number(raw)
      if (!raw.trim() || !Number.isInteger(value) || value < 1 || value > 100000) {
        push(key, '长度须为 1 至 100000 的整数毫米')
        return 0
      }
      return value
    }
    // Optional end-trim allowance: blank means 0.
    const parseAllowance = (raw: string, key: string): number => {
      if (!raw.trim()) return 0
      const value = Number(raw)
      if (!Number.isInteger(value) || value < 0 || value > MAX_ALLOWANCE) {
        push(key, `余量须为 0 至 ${MAX_ALLOWANCE} 的整数毫米`)
        return 0
      }
      return value
    }
    const roll_length = parseLen(rollLength, 'roll_length')
    const kerf_width = parseLen(kerfWidth, 'kerf_width')
    const segments = rows.map((row, i) => {
      const id = row.id.trim()
      if (!id) push(`segments.${i}.id`, '编号不能为空')
      return {
        id,
        length: parseLen(row.length, `segments.${i}.length`),
        allowance: parseAllowance(row.allowance, `segments.${i}.allowance`),
      }
    })
    if (local.size > 0) {
      setErrors(local)
      return
    }

    setSubmitting(true)
    try {
      const plan = await createPlan({
        roll_length,
        kerf_width,
        segments,
        ...(sourceId !== null ? { source_plan_id: sourceId } : {}),
      })
      navigate(`/plans/${plan.id}`)
    } catch (err) {
      // 校验失败时表单状态原样保留，领班可直接修正后重新提交。
      if (err instanceof ApiError) {
        if (err.fieldErrors.length > 0) {
          const grouped = groupErrors(err.fieldErrors)
          // 字段错误仍按原方式标回对应输入框，不弹顶部横幅；来源失效时
          // 额外给出重新选择来源的提示。
          setErrors(grouped)
          const sourceMsg = grouped.get('source_plan_id')
          if (sourceMsg) {
            // 来源已失效：编辑内容全部保留，提示重新选择来源。
            setSourceError(sourceMsg[0])
            setSourcePick(sourceId !== null ? String(sourceId) : '')
          }
        } else {
          setTopError(err.message)
        }
      } else {
        setTopError('网络异常，请稍后重试')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="plan-form" onSubmit={onSubmit} noValidate>
      {topError && (
        <p className="error-banner" role="alert">
          {topError}
        </p>
      )}

      {sourceId !== null && !sourceError && (
        <p className="source-banner" data-testid="source-banner">
          基于方案 #{sourceId} 调整：卷长、锯口与线段已原样带入，可直接修改后重新求解；
          原方案保持只读。
          <Link to={`/plans/${sourceId}`}>查看原方案 #{sourceId}</Link>
        </p>
      )}
      {sourceError && (
        <div className="error-banner" role="alert" data-testid="source-error">
          <p>
            来源方案无效（{sourceError}），请重新选择来源；当前编辑内容已全部保留。
          </p>
          <div className="source-reselect">
            <label>
              来源方案编号
              <input
                data-testid="source-plan-input"
                type="number"
                min={1}
                step={1}
                value={sourcePick}
                onChange={(e) => setSourcePick(e.target.value)}
              />
            </label>
            <button
              type="button"
              data-testid="source-plan-confirm"
              onClick={confirmSourcePick}
            >
              确认来源
            </button>
            <Link to="/plans" data-testid="source-repick-list">
              从历史列表重新选择
            </Link>
          </div>
        </div>
      )}

      <div className="form-grid">
        <label>
          卷长（mm）
          <input
            data-testid="roll-length"
            type="number"
            min={1}
            max={100000}
            step={1}
            required
            value={rollLength}
            onChange={(e) => setRollLength(e.target.value)}
          />
          <FieldErrors messages={fieldError('roll_length')} />
        </label>
        <label>
          锯口宽度（mm）
          <input
            data-testid="kerf-width"
            type="number"
            min={1}
            max={100000}
            step={1}
            required
            value={kerfWidth}
            onChange={(e) => setKerfWidth(e.target.value)}
          />
          <FieldErrors messages={fieldError('kerf_width')} />
        </label>
      </div>

      <fieldset>
        <legend>需求线段（{rows.length} / {MAX_SEGMENTS} 条）</legend>
        {rows.map((row, i) => (
          <div className="segment-row" key={row.key}>
            <span className="segment-index">#{i + 1}</span>
            <label>
              编号
              <input
                data-testid={`segment-id-${i}`}
                type="text"
                maxLength={32}
                required
                value={row.id}
                onChange={(e) => setRows(updateRow(rows, row.key, { id: e.target.value }))}
              />
              <FieldErrors messages={fieldError(`segments.${i}.id`)} />
            </label>
            <label>
              长度（mm）
              <input
                data-testid={`segment-length-${i}`}
                type="number"
                min={1}
                max={100000}
                step={1}
                required
                value={row.length}
                onChange={(e) =>
                  setRows(updateRow(rows, row.key, { length: e.target.value }))
                }
              />
              <FieldErrors messages={fieldError(`segments.${i}.length`)} />
            </label>
            <label>
              余量（mm，可空）
              <input
                data-testid={`segment-allowance-${i}`}
                type="number"
                min={0}
                max={MAX_ALLOWANCE}
                step={1}
                placeholder="0"
                value={row.allowance}
                onChange={(e) =>
                  setRows(updateRow(rows, row.key, { allowance: e.target.value }))
                }
              />
              <FieldErrors messages={fieldError(`segments.${i}.allowance`)} />
            </label>
            <button
              type="button"
              data-testid={`remove-segment-${i}`}
              disabled={rows.length <= 1}
              onClick={() => setRows(removeRow(rows, row.key))}
            >
              删除
            </button>
          </div>
        ))}
        <button
          type="button"
          data-testid="add-segment"
          disabled={rows.length >= MAX_SEGMENTS}
          onClick={() => setRows(addRow(rows))}
        >
          添加线段
        </button>
      </fieldset>

      <button type="submit" data-testid="submit-plan" disabled={submitting}>
        {submitting ? '计算中…' : '生成裁切方案'}
      </button>
    </form>
  )
}
