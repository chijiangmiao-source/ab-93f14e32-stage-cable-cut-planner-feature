import type { FieldError, PlanCreateInput, PlanOut, PlanSummary } from './types'

export class ApiError extends Error {
  readonly status: number
  readonly fieldErrors: FieldError[]

  constructor(status: number, message: string, fieldErrors: FieldError[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let fieldErrors: FieldError[] = []
  let message = `请求失败（HTTP ${res.status}）`
  try {
    const body: unknown = await res.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      if (Array.isArray(detail)) {
        fieldErrors = detail as FieldError[]
        message = '输入校验未通过，请检查标红字段'
      } else if (typeof detail === 'string') {
        message = detail
      }
    }
  } catch {
    // keep the default message
  }
  return new ApiError(res.status, message, fieldErrors)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as T
}

export function createPlan(input: PlanCreateInput): Promise<PlanOut> {
  return request<PlanOut>('/api/plans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

export function listPlans(): Promise<PlanSummary[]> {
  return request<PlanSummary[]>('/api/plans')
}

export function getPlan(id: string | number): Promise<PlanOut> {
  return request<PlanOut>(`/api/plans/${id}`)
}

/** Record the next cut of one roll. `position` is the 1-based canonical cut
 *  position the page currently believes is next; the server answers 409 when
 *  the page is stale or the order is wrong. */
export function completeCut(
  planId: number,
  rollPosition: number,
  position: number,
): Promise<PlanOut> {
  return request<PlanOut>(
    `/api/plans/${planId}/rolls/${rollPosition}/complete`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ position }),
    },
  )
}

/** Undo the last completed cut of one roll only. */
export function undoCut(
  planId: number,
  rollPosition: number,
  position: number,
): Promise<PlanOut> {
  return request<PlanOut>(
    `/api/plans/${planId}/rolls/${rollPosition}/undo`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ position }),
    },
  )
}
