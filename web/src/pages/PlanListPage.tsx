import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listPlans } from '../api'
import type { PlanSummary } from '../types'

export default function PlanListPage() {
  const [plans, setPlans] = useState<PlanSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listPlans()
      .then(setPlans)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : '加载失败'),
      )
  }, [])

  return (
    <section>
      <h2>历史方案</h2>
      {error && <p className="error-banner">{error}</p>}
      {plans === null && !error && <p>加载中…</p>}
      {plans !== null && plans.length === 0 && <p>暂无方案，请先新建。</p>}
      {plans !== null && plans.length > 0 && (
        <table className="plan-table">
          <thead>
            <tr>
              <th>编号</th>
              <th>创建时间</th>
              <th>卷长 (mm)</th>
              <th>锯口 (mm)</th>
              <th>线段数</th>
              <th>线卷数</th>
              <th>总余料 (mm)</th>
              <th>源自方案</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {plans.map((p) => (
              <tr key={p.id}>
                <td>{p.id}</td>
                <td>{new Date(p.created_at).toLocaleString()}</td>
                <td>{p.roll_length}</td>
                <td>{p.kerf_width}</td>
                <td>{p.segment_count}</td>
                <td>{p.rolls_used}</td>
                <td>{p.total_leftover}</td>
                <td>
                  {p.source_plan_id !== null && p.source_plan_id !== undefined ? (
                    <Link
                      to={`/plans/${p.source_plan_id}`}
                      data-testid={`source-link-${p.id}`}
                    >
                      #{p.source_plan_id}
                    </Link>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  <Link to={`/plans/${p.id}`}>查看</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
