import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError, completeCut, getPlan, undoCut } from '../api'
import PlanDetailView from '../components/PlanDetailView'
import type { PlanOut } from '../types'

export default function PlanDetailPage() {
  const { id } = useParams<{ id: string }>()
  const planId = Number(id)
  const [plan, setPlan] = useState<PlanOut | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Locks all complete/undo buttons while a request is in flight, preventing
  // duplicate actions from double clicks.
  const inflight = useRef(false)

  const reload = useCallback(async () => {
    const fresh = await getPlan(planId)
    setPlan(fresh)
  }, [planId])

  useEffect(() => {
    if (!id) return
    getPlan(id)
      .then(setPlan)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : '加载失败'),
      )
  }, [id])

  /** Run one progress mutation. The server always returns the full updated
   *  plan, so its response becomes the single source of truth (progress on
   *  other rolls is never overwritten locally). On 409 the page was stale or
   *  the action was out of order: show the server message and re-pull the
   *  detail to display the real progress. */
  async function mutate(
    kind: 'complete' | 'undo',
    rollPosition: number,
    cutPosition: number,
  ) {
    if (inflight.current) return
    inflight.current = true
    setBusy(true)
    setNotice(null)
    try {
      const updated =
        kind === 'complete'
          ? await completeCut(planId, rollPosition, cutPosition)
          : await undoCut(planId, rollPosition, cutPosition)
      setPlan(updated)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setNotice(`${err.message}，已为你刷新为最新进度`)
      } else {
        setNotice(err instanceof Error ? err.message : '操作失败，请稍后重试')
      }
      try {
        await reload()
      } catch {
        // keep the conflict notice if the refetch itself fails
      }
    } finally {
      inflight.current = false
      setBusy(false)
    }
  }

  return (
    <section>
      {error && <p className="error-banner">{error}</p>}
      {!plan && !error && <p>加载中…</p>}
      {notice && (
        <p className="conflict-banner" role="alert" data-testid="conflict-banner">
          {notice}
        </p>
      )}
      {plan && (
        <>
          <h2>方案 #{plan.id}</h2>
          <PlanDetailView
            plan={plan}
            busy={busy}
            onComplete={(rollPosition, cutPosition) =>
              void mutate('complete', rollPosition, cutPosition)
            }
            onUndo={(rollPosition, cutPosition) =>
              void mutate('undo', rollPosition, cutPosition)
            }
          />
        </>
      )}
    </section>
  )
}
