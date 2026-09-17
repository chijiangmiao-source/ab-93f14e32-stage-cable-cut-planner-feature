import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import PlanDetailView from '../components/PlanDetailView'
import type { PlanOut } from '../types'

function makePlan(overrides: Partial<PlanOut> = {}): PlanOut {
  return {
    id: 7,
    roll_length: 1000,
    kerf_width: 10,
    rolls_used: 2,
    total_kerf_count: 1,
    total_leftover: 400,
    completed_segment_count: 0,
    created_at: '2026-09-12T08:00:00Z',
    source_plan_id: null,
    rolls: [
      {
        position: 1,
        segments: [{ id: 'A', length: 600, allowance: 0, bundle: null, completed_at: null }],
        kerf_count: 0,
        used_length: 600,
        leftover: 400,
        completed_count: 0,
      },
      {
        position: 2,
        segments: [
          { id: 'B', length: 590, allowance: 0, bundle: null, completed_at: null },
          { id: 'C', length: 400, allowance: 0, bundle: null, completed_at: null },
        ],
        kerf_count: 1,
        used_length: 1000,
        leftover: 0,
        completed_count: 0,
      },
    ],
    ...overrides,
  }
}

function renderView(
  viewPlan: PlanOut = makePlan(),
  busy = false,
  onComplete = vi.fn(),
  onUndo = vi.fn(),
) {
  return render(
    <MemoryRouter>
      <PlanDetailView
        plan={viewPlan}
        busy={busy}
        onComplete={onComplete}
        onUndo={onUndo}
      />
    </MemoryRouter>,
  )
}

describe('PlanDetailView', () => {
  it('shows totals and per-roll cutting order, kerfs and leftovers', () => {
    const { container } = renderView()
    const text = container.textContent ?? ''

    expect(screen.getByText('第 1 卷')).toBeInTheDocument()
    expect(screen.getByText('第 2 卷')).toBeInTheDocument()

    // every segment states delivery, zero allowance and cut length explicitly
    expect(text).toContain('A（交付 600 mm + 余量 0 mm = 下料 600 mm）')
    expect(text).toContain(
      'B（交付 590 mm + 余量 0 mm = 下料 590 mm） → C（交付 400 mm + 余量 0 mm = 下料 400 mm）',
    )

    // per-roll arithmetic: 590+400 + 1×10 kerf = 1000 ≤ 1000, leftover 0
    expect(text).toContain('990（线长合计）+ 1 × 10（锯口）= 1000 mm ≤ 1000 mm；余料 0 mm；锯口 1 次')
    expect(text).toContain('600（线长合计）+ 0 × 10（锯口）= 600 mm ≤ 1000 mm；余料 400 mm；锯口 0 次')

    // totals — progress starts at 0 and original solution fields still render
    expect(text).toContain('总余料')
    expect(text).toContain('400 mm')
    expect(screen.getByTestId('overall-progress')).toHaveTextContent('0 / 3 段')
  })

  it('highlights the first pending cut of each roll and aggregates progress', () => {
    const plan = makePlan({
      completed_segment_count: 1,
      rolls: [
        {
          position: 1,
          segments: [{ id: 'A', length: 600, allowance: 0, bundle: null, completed_at: null }],
          kerf_count: 0,
          used_length: 600,
          leftover: 400,
          completed_count: 0,
        },
        {
          position: 2,
          segments: [
            {
              id: 'B',
              length: 590,
              allowance: 0,
              bundle: null,
              completed_at: '2026-09-12T09:00:00Z',
            },
            { id: 'C', length: 400, allowance: 0, bundle: null, completed_at: null },
          ],
          kerf_count: 1,
          used_length: 1000,
          leftover: 0,
          completed_count: 1,
        },
      ],
    })
    renderView(plan)

    // roll 1: A is its next cut; roll 2: B done, C is the next cut
    expect(screen.getByTestId('cut-1-1')).toHaveClass('cut-status-next')
    expect(screen.getByTestId('cut-2-1')).toHaveClass('cut-status-done')
    expect(screen.getByTestId('cut-2-2')).toHaveClass('cut-status-next')
    expect(screen.getByTestId('overall-progress')).toHaveTextContent('1 / 3 段')
    expect(screen.getByTestId('roll-progress-2')).toHaveTextContent('已完成 1 / 2 段')

    // actions are enabled purely from server state
    expect(screen.getByTestId('complete-roll-1')).toBeEnabled()
    expect(screen.getByTestId('complete-roll-2')).toBeEnabled()
    expect(screen.getByTestId('undo-roll-1')).toBeDisabled()
    expect(screen.getByTestId('undo-roll-2')).toBeEnabled()
  })

  it('completes the next cut and undoes the last cut using canonical positions', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    const onUndo = vi.fn()
    const { rerender } = renderView(makePlan(), false, onComplete, onUndo)

    await user.click(screen.getByTestId('complete-roll-2'))
    expect(onComplete).toHaveBeenCalledWith(2, 1)
    expect(screen.getByTestId('complete-roll-2')).toHaveTextContent(
      '完成此段（第 1 段：B）',
    )

    // nothing completed yet -> undo is offered but reports no undoable cut
    expect(screen.getByTestId('undo-roll-2')).toBeDisabled()

    // simulate the server returning the plan with B finished
    const afterB = makePlan({
      completed_segment_count: 1,
      rolls: [
        makePlan().rolls[0],
        {
          ...makePlan().rolls[1],
          completed_count: 1,
          segments: [
            { id: 'B', length: 590, allowance: 0, bundle: null, completed_at: '2026-09-12T09:00:00Z' },
            { id: 'C', length: 400, allowance: 0, bundle: null, completed_at: null },
          ],
        },
      ],
    })
    rerender(
      <MemoryRouter>
        <PlanDetailView
          plan={afterB}
          busy={false}
          onComplete={onComplete}
          onUndo={onUndo}
        />
      </MemoryRouter>,
    )
    await user.click(screen.getByTestId('undo-roll-2'))
    // only the last completed cut (position 1) is offered for undo
    expect(onUndo).toHaveBeenCalledWith(2, 1)
  })

  it('disables every action while a request is in flight', () => {
    renderView(makePlan(), true)
    expect(screen.getByTestId('complete-roll-1')).toBeDisabled()
    expect(screen.getByTestId('complete-roll-2')).toBeDisabled()
    // undo buttons start disabled here (no completed cuts) and stay locked
    expect(screen.getByTestId('undo-roll-1')).toBeDisabled()
    expect(screen.getByTestId('undo-roll-2')).toBeDisabled()
  })

  it('locks completion on a fully finished roll while keeping undo available', () => {
    const finished = makePlan({
      completed_segment_count: 3,
      rolls: [
        {
          position: 1,
          segments: [
            { id: 'A', length: 600, allowance: 0, bundle: null, completed_at: '2026-09-12T09:00:00Z' },
          ],
          kerf_count: 0,
          used_length: 600,
          leftover: 400,
          completed_count: 1,
        },
        {
          position: 2,
          segments: [
            { id: 'B', length: 590, allowance: 0, bundle: null, completed_at: '2026-09-12T09:01:00Z' },
            { id: 'C', length: 400, allowance: 0, bundle: null, completed_at: '2026-09-12T09:02:00Z' },
          ],
          kerf_count: 1,
          used_length: 1000,
          leftover: 0,
          completed_count: 2,
        },
      ],
    })
    renderView(finished)
    expect(screen.getByTestId('complete-roll-2')).toBeDisabled()
    expect(screen.getByTestId('complete-roll-2')).toHaveTextContent('本卷已全部完成')
    expect(screen.getByTestId('undo-roll-2')).toBeEnabled()
    expect(screen.getByTestId('overall-progress')).toHaveTextContent('3 / 3 段（全部完成）')
  })

  it('offers an "adjust from this plan" entry point', () => {
    renderView()
    const adjust = screen.getByTestId('adjust-from-plan')
    expect(adjust.textContent).toContain('基于此方案调整')
    expect(adjust.getAttribute('href')).toBe('/?from=7')
  })

  it('hides the source line for plans without a source', () => {
    renderView(makePlan({ source_plan_id: null }))
    expect(screen.queryByTestId('source-line')).not.toBeInTheDocument()
    expect(screen.queryByText('源自方案')).not.toBeInTheDocument()
  })

  it('links to the source plan when provenance exists', () => {
    renderView(makePlan({ id: 9, source_plan_id: 7 }))
    const sourceLine = screen.getByTestId('source-line')
    const link = sourceLine.querySelector('a')
    expect(link).not.toBeNull()
    expect(link?.getAttribute('href')).toBe('/plans/7')
    expect(link?.textContent).toBe('#7')
    // the adjust entry of the new plan points at the new plan itself
    expect(screen.getByTestId('adjust-from-plan').getAttribute('href')).toBe('/?from=9')
  })

  it('shows allowance and recomputes the roll from actual cut lengths', () => {
    const withAllowance = makePlan({
      rolls_used: 3,
      total_kerf_count: 0,
      total_leftover: 1360,
      rolls: [
        {
          position: 1,
          segments: [{ id: 'A', length: 600, allowance: 0, bundle: null, completed_at: null }],
          kerf_count: 0,
          used_length: 600,
          leftover: 400,
          completed_count: 0,
        },
        {
          position: 2,
          segments: [{ id: 'B', length: 590, allowance: 0, bundle: null, completed_at: null }],
          kerf_count: 0,
          used_length: 590,
          leftover: 410,
          completed_count: 0,
        },
        {
          position: 3,
          segments: [{ id: 'C', length: 400, allowance: 50, bundle: null, completed_at: null }],
          kerf_count: 0,
          used_length: 450,
          leftover: 550,
          completed_count: 0,
        },
      ],
    })
    const { container } = renderView(withAllowance)
    const text = container.textContent ?? ''
    expect(text).toContain('C（交付 400 mm + 余量 50 mm = 下料 450 mm）')
    // zero-allowance segments in the same plan still state the zero allowance
    expect(text).toContain('A（交付 600 mm + 余量 0 mm = 下料 600 mm）')
    expect(text).toContain('B（交付 590 mm + 余量 0 mm = 下料 590 mm）')
    expect(text).toContain(
      '450（下料合计 = 交付 400 mm + 余量 50 mm）+ 0 × 10（锯口）= 450 mm ≤ 1000 mm；余料 550 mm；锯口 0 次',
    )
  })

  it('shows bundle ids beside the cutting order, none for loose segments', () => {
    const bundled = makePlan({
      rolls_used: 3,
      total_kerf_count: 1,
      total_leftover: 110,
      rolls: [
        {
          position: 1,
          segments: [
            { id: 'A', length: 40, allowance: 0, bundle: 'G1', completed_at: null },
            { id: 'B', length: 40, allowance: 0, bundle: 'G1', completed_at: null },
          ],
          kerf_count: 1,
          used_length: 90,
          leftover: 10,
          completed_count: 0,
        },
        {
          position: 2,
          segments: [
            { id: 'C', length: 50, allowance: 0, bundle: null, completed_at: null },
          ],
          kerf_count: 0,
          used_length: 50,
          leftover: 50,
          completed_count: 0,
        },
        {
          position: 3,
          segments: [
            { id: 'D', length: 50, allowance: 0, bundle: null, completed_at: null },
          ],
          kerf_count: 0,
          used_length: 50,
          leftover: 50,
          completed_count: 0,
        },
      ],
    })
    const { container } = renderView(bundled)

    // The bundle id rides next to the original cutting-order entries.
    const orderLines = container.querySelectorAll('.cutting-order')
    expect(orderLines[0].textContent).toContain(
      'A（交付 40 mm + 余量 0 mm = 下料 40 mm）［套组 G1］ → B（交付 40 mm + 余量 0 mm = 下料 40 mm）［套组 G1］',
    )
    // Unbundled rolls keep the plain cutting order with no bundle tag.
    expect(orderLines[1].textContent).toContain('C（交付 50 mm + 余量 0 mm = 下料 50 mm）')
    expect(orderLines[1].textContent).not.toContain('套组')
    expect(orderLines[2].textContent).not.toContain('套组')

    // Progress stays per segment: roll 1 still offers its two cuts one by one.
    expect(screen.getByTestId('roll-progress-1')).toHaveTextContent('已完成 0 / 2 段')
    expect(screen.getByTestId('cut-1-1')).toHaveClass('cut-status-next')
    expect(screen.getByTestId('cut-1-2')).toHaveClass('cut-status-pending')
  })
})
