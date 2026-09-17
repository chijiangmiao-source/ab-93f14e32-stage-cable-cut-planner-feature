import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getPlan } from '../api'
import PlanForm from '../components/PlanForm'
import type { PlanFormInitial } from '../components/PlanForm'

export default function NewPlanPage() {
  const [params] = useSearchParams()
  const from = params.get('from')

  // undefined = still loading, null = ordinary creation (no source),
  // object = the source plan's inputs carried over verbatim.
  const [initial, setInitial] = useState<PlanFormInitial | null | undefined>(
    from ? undefined : null,
  )
  const [sourceId, setSourceId] = useState<number | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (!from) {
      setInitial(null)
      setSourceId(null)
      return
    }
    let cancelled = false
    getPlan(from)
      .then((plan) => {
        if (cancelled) return
        // Flatten cuts in roll/cut order; the solver canonicalizes anyway.
        setInitial({
          roll_length: plan.roll_length,
          kerf_width: plan.kerf_width,
          segments: plan.rolls.flatMap((r) => r.segments),
        })
        setSourceId(plan.id)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setLoadError(err instanceof Error ? err.message : '来源方案加载失败')
        setInitial(null)
      })
    return () => {
      cancelled = true
    }
  }, [from])

  return (
    <section>
      <h2>{from ? '基于已有方案调整' : '新建裁切方案'}</h2>
      {loadError && (
        <p className="error-banner" role="alert" data-testid="from-load-error">
          来源方案加载失败：{loadError}，可直接新建或
          <Link to="/plans">返回历史方案重新选择</Link>。
        </p>
      )}
      {from && initial === undefined && !loadError && <p>正在载入原方案…</p>}
      {initial !== undefined && (
        <PlanForm
          key={from ? `adjust-${from}` : 'new'}
          initial={initial ?? undefined}
          sourcePlanId={sourceId}
        />
      )}
    </section>
  )
}
