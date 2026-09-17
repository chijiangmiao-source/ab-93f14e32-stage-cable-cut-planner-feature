import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import PlanDetailPage from '../pages/PlanDetailPage'
import type { PlanOut } from '../types'

function plan(
  progress: boolean[][] = [
    [false],
    [false, false],
  ],
): PlanOut {
  // roll 1 = [A], roll 2 = [B, C]; each boolean says whether that cut carries
  // a completion timestamp.
  const stamp = '2026-09-12T09:00:00Z'
  const done2 = progress[1]
  const count2 = done2.filter(Boolean).length
  const done1 = progress[0]
  const count1 = done1.filter(Boolean).length
  return {
    id: 42,
    roll_length: 1000,
    kerf_width: 10,
    rolls_used: 2,
    total_kerf_count: 1,
    total_leftover: 400,
    completed_segment_count: count1 + count2,
    created_at: '2026-09-12T08:00:00Z',
    source_plan_id: null,
    rolls: [
      {
        position: 1,
        segments: [{ id: 'A', length: 600, allowance: 0, bundle: null, completed_at: done1[0] ? stamp : null }],
        kerf_count: 0,
        used_length: 600,
        leftover: 400,
        completed_count: count1,
      },
      {
        position: 2,
        segments: [
          { id: 'B', length: 590, allowance: 0, bundle: null, completed_at: done2[0] ? stamp : null },
          { id: 'C', length: 400, allowance: 0, bundle: null, completed_at: done2[1] ? stamp : null },
        ],
        kerf_count: 1,
        used_length: 1000,
        leftover: 0,
        completed_count: count2,
      },
    ],
  }
}

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/plans/42']}>
      <Routes>
        <Route path="/plans/:id" element={<PlanDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('PlanDetailPage progress flow', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('completes two cuts in order using the server response as truth', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock
      .mockResolvedValueOnce(jsonResponse(plan())) // initial GET
      .mockResolvedValueOnce(jsonResponse(plan([[false], [true, false]]))) // complete B
      .mockResolvedValueOnce(jsonResponse(plan([[false], [true, true]]))) // complete C

    renderPage()

    await waitFor(() =>
      expect(screen.getByTestId('overall-progress')).toHaveTextContent('0 / 3 段'),
    )
    const user = userEvent.setup()
    await user.click(screen.getByTestId('complete-roll-2'))
    await waitFor(() =>
      expect(screen.getByTestId('overall-progress')).toHaveTextContent('1 / 3 段'),
    )
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/plans/42/rolls/2/complete',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ position: 1 }),
      }),
    )

    // the next cut offered on roll 2 is now C (position 2)
    await user.click(screen.getByTestId('complete-roll-2'))
    await waitFor(() =>
      expect(screen.getByTestId('overall-progress')).toHaveTextContent('2 / 3 段'),
    )
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/plans/42/rolls/2/complete',
      expect.objectContaining({ body: JSON.stringify({ position: 2 }) }),
    )
  })

  it('prevents duplicate actions while a request is in flight', async () => {
    const fetchMock = vi.mocked(fetch)
    let resolveComplete: (r: Response) => void = () => {}
    fetchMock
      .mockResolvedValueOnce(jsonResponse(plan()))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveComplete = resolve
          }),
      )

    renderPage()
    const user = userEvent.setup()
    await waitFor(() =>
      expect(screen.getByTestId('complete-roll-2')).toBeEnabled(),
    )
    await user.click(screen.getByTestId('complete-roll-2'))

    // all actions lock while the first request is pending; a second click on
    // either roll must not fire another request
    await waitFor(() =>
      expect(screen.getByTestId('complete-roll-2')).toBeDisabled(),
    )
    expect(screen.getByTestId('complete-roll-1')).toBeDisabled()
    expect(screen.getByTestId('undo-roll-2')).toBeDisabled()
    await user.click(screen.getByTestId('complete-roll-1'))
    expect(fetchMock).toHaveBeenCalledTimes(2) // GET + one POST only

    resolveComplete?.(jsonResponse(plan([[false], [true, false]])))
    await waitFor(() =>
      expect(screen.getByTestId('complete-roll-2')).toBeEnabled(),
    )
  })

  it('shows the conflict and refetches on a 409, without touching other rolls', async () => {
    const fetchMock = vi.mocked(fetch)
    // Server truth: B is already done (stale page believed position 1 pending).
    const serverTruth = plan([[false], [true, false]])
    fetchMock
      .mockResolvedValueOnce(jsonResponse(plan()))
      // stale complete of position 1 is rejected
      .mockResolvedValueOnce(
        jsonResponse(
          { detail: '只能按顺序完成第 2 段，页面可能已过期，请刷新' },
          { status: 409 },
        ),
      )
      // conflict recovery: re-pull the real detail
      .mockResolvedValueOnce(jsonResponse(serverTruth))

    renderPage()
    const user = userEvent.setup()
    await waitFor(() =>
      expect(screen.getByTestId('overall-progress')).toHaveTextContent('0 / 3 段'),
    )
    await user.click(screen.getByTestId('complete-roll-2'))

    await waitFor(() =>
      expect(screen.getByTestId('conflict-banner')).toBeInTheDocument(),
    )
    // refetched truth: B done, C highlighted next on roll 2; roll 1 untouched
    await waitFor(() =>
      expect(screen.getByTestId('overall-progress')).toHaveTextContent('1 / 3 段'),
    )
    const roll2 = screen.getByTestId('roll-progress-2')
    expect(roll2).toHaveTextContent('已完成 1 / 2 段')
    expect(screen.getByTestId('cut-2-1')).toHaveClass('cut-status-done')
    expect(screen.getByTestId('cut-2-2')).toHaveClass('cut-status-next')
    expect(screen.getByTestId('cut-1-1')).toHaveClass('cut-status-next')
  })

  it('undoes only the last completed cut', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock
      .mockResolvedValueOnce(jsonResponse(plan([[false], [true, true]])))
      .mockResolvedValueOnce(jsonResponse(plan([[false], [true, false]])))

    renderPage()
    const user = userEvent.setup()
    await waitFor(() =>
      expect(screen.getByTestId('undo-roll-2')).toBeEnabled(),
    )
    await user.click(screen.getByTestId('undo-roll-2'))

    await waitFor(() =>
      expect(screen.getByTestId('roll-progress-2')).toHaveTextContent(
        '已完成 1 / 2 段',
      ),
    )
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/plans/42/rolls/2/undo',
      expect.objectContaining({ body: JSON.stringify({ position: 2 }) }),
    )
  })
})
