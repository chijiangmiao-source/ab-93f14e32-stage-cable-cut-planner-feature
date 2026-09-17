import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const createPlanMock = vi.fn()

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, createPlan: (...args: unknown[]) => createPlanMock(...args) }
})

import PlanForm from '../components/PlanForm'
import type { PlanFormInitial } from '../components/PlanForm'
import { ApiError } from '../api'

const initial: PlanFormInitial = {
  roll_length: 1000,
  kerf_width: 10,
  segments: [
    { id: 'A', length: 600 },
    { id: 'B', length: 590 },
    { id: 'C', length: 400, allowance: 50 },
  ],
}

function renderForm(props: Parameters<typeof PlanForm>[0] = {}) {
  return render(
    <MemoryRouter>
      <PlanForm {...props} />
    </MemoryRouter>,
  )
}

describe('PlanForm adjustment flow', () => {
  beforeEach(() => {
    createPlanMock.mockReset()
  })

  it('carries the source inputs over verbatim and shows the provenance banner', () => {
    renderForm({ initial, sourcePlanId: 5 })

    expect(screen.getByTestId('roll-length')).toHaveValue(1000)
    expect(screen.getByTestId('kerf-width')).toHaveValue(10)
    expect(screen.getByTestId('segment-id-0')).toHaveValue('A')
    expect(screen.getByTestId('segment-length-0')).toHaveValue(600)
    expect(screen.getByTestId('segment-id-2')).toHaveValue('C')
    expect(screen.getByTestId('segment-length-2')).toHaveValue(400)
    expect(screen.getByTestId('segment-allowance-2')).toHaveValue(50)

    const banner = screen.getByTestId('source-banner')
    expect(banner.textContent).toContain('基于方案 #5 调整')
    expect(banner.querySelector('a')?.getAttribute('href')).toBe('/plans/5')
  })

  it('sends source_plan_id on submit while edits are included', async () => {
    createPlanMock.mockResolvedValueOnce({ id: 51 })
    renderForm({ initial, sourcePlanId: 5 })

    // edit one segment: C 400 -> 300
    fireEvent.change(screen.getByTestId('segment-length-2'), {
      target: { value: '300' },
    })
    fireEvent.click(screen.getByTestId('submit-plan'))

    await waitFor(() => expect(createPlanMock).toHaveBeenCalledTimes(1))
    const body = createPlanMock.mock.calls[0][0]
    expect(body.source_plan_id).toBe(5)
    expect(body.roll_length).toBe(1000)
    expect(body.segments.map((s: { id: string }) => s.id)).toEqual(['A', 'B', 'C'])
    expect(body.segments[2].length).toBe(300)
  })

  it('omits source_plan_id for ordinary creation', async () => {
    createPlanMock.mockResolvedValueOnce({ id: 1 })
    renderForm()
    fireEvent.click(screen.getByTestId('submit-plan'))

    await waitFor(() => expect(createPlanMock).toHaveBeenCalledTimes(1))
    const body = createPlanMock.mock.calls[0][0]
    expect(body).not.toHaveProperty('source_plan_id')
  })

  it('keeps all edits when the source is invalid and allows re-selecting it', async () => {
    createPlanMock.mockRejectedValueOnce(
      new ApiError(422, '输入校验未通过', [
        {
          loc: ['source_plan_id'],
          msg: 'source plan 5 not found',
          type: 'value_error',
        },
      ]),
    )
    createPlanMock.mockResolvedValueOnce({ id: 60 })
    renderForm({ initial, sourcePlanId: 5 })

    // the foreman already edited B before submitting
    fireEvent.change(screen.getByTestId('segment-length-1'), {
      target: { value: '380' },
    })
    fireEvent.click(screen.getByTestId('submit-plan'))

    // error banner appears, every edit stays in the form
    const sourceError = await screen.findByTestId('source-error')
    expect(sourceError.textContent).toContain('来源方案无效')
    expect(screen.getByTestId('segment-length-1')).toHaveValue(380)
    expect(screen.getByTestId('segment-length-0')).toHaveValue(600)
    expect(screen.getByTestId('roll-length')).toHaveValue(1000)

    // re-pick a valid source without losing edits
    fireEvent.change(screen.getByTestId('source-plan-input'), {
      target: { value: '8' },
    })
    fireEvent.click(screen.getByTestId('source-plan-confirm'))
    await waitFor(() =>
      expect(screen.queryByTestId('source-error')).not.toBeInTheDocument(),
    )
    fireEvent.click(screen.getByTestId('submit-plan'))

    await waitFor(() => expect(createPlanMock).toHaveBeenCalledTimes(2))
    const body = createPlanMock.mock.calls[1][0]
    expect(body.source_plan_id).toBe(8)
    expect(body.segments[1].length).toBe(380)
  })
})

describe('PlanForm bundle groups', () => {
  beforeEach(() => {
    createPlanMock.mockReset()
  })

  it('renders a blank bundle input per row by default', () => {
    renderForm()
    expect(screen.getByTestId('segment-bundle-0')).toHaveValue('')
    expect(screen.getByTestId('segment-bundle-1')).toHaveValue('')
    expect(screen.getByTestId('segment-bundle-2')).toHaveValue('')
  })

  it('carries bundle ids from the source plan verbatim', () => {
    renderForm({
      initial: {
        roll_length: 100,
        kerf_width: 10,
        segments: [
          { id: 'A', length: 40, bundle: 'G1' },
          { id: 'B', length: 40, bundle: 'G1' },
          { id: 'C', length: 50 },
        ],
      },
      sourcePlanId: 5,
    })
    expect(screen.getByTestId('segment-bundle-0')).toHaveValue('G1')
    expect(screen.getByTestId('segment-bundle-1')).toHaveValue('G1')
    expect(screen.getByTestId('segment-bundle-2')).toHaveValue('')
  })

  it('sends bundle ids for filled rows and omits blank ones', async () => {
    createPlanMock.mockResolvedValueOnce({ id: 77 })
    renderForm()
    fireEvent.change(screen.getByTestId('segment-bundle-0'), {
      target: { value: 'G1' },
    })
    fireEvent.change(screen.getByTestId('segment-bundle-1'), {
      target: { value: 'G1' },
    })
    fireEvent.click(screen.getByTestId('submit-plan'))

    await waitFor(() => expect(createPlanMock).toHaveBeenCalledTimes(1))
    const body = createPlanMock.mock.calls[0][0]
    expect(body.segments[0].bundle).toBe('G1')
    expect(body.segments[1].bundle).toBe('G1')
    expect(body.segments[2]).not.toHaveProperty('bundle')
  })

  it('rejects a malformed bundle id locally without calling the api', () => {
    renderForm()
    fireEvent.change(screen.getByTestId('segment-bundle-0'), {
      target: { value: 'bad bundle' },
    })
    fireEvent.click(screen.getByTestId('submit-plan'))

    expect(createPlanMock).not.toHaveBeenCalled()
    expect(screen.getByText(/套组编号须为/)).toBeInTheDocument()
    // the invalid input stays in place for correction
    expect(screen.getByTestId('segment-bundle-0')).toHaveValue('bad bundle')
  })

  it('maps a server bundle error back to the bundle inputs and keeps the form', async () => {
    createPlanMock.mockRejectedValueOnce(
      new ApiError(422, '输入校验未通过', [
        {
          loc: ['segments', 0, 'bundle'],
          msg: "bundle 'G1' needs 135 mm (cut lengths + 1 kerfs) and exceeds usable roll length 100 by 35 mm",
          type: 'value_error',
        },
        {
          loc: ['segments', 1, 'bundle'],
          msg: "bundle 'G1' needs 135 mm (cut lengths + 1 kerfs) and exceeds usable roll length 100 by 35 mm",
          type: 'value_error',
        },
      ]),
    )
    renderForm()
    fireEvent.change(screen.getByTestId('segment-bundle-0'), {
      target: { value: 'G1' },
    })
    fireEvent.change(screen.getByTestId('segment-bundle-1'), {
      target: { value: 'G1' },
    })
    fireEvent.click(screen.getByTestId('submit-plan'))

    // both bundle inputs are flagged with the excess in millimetres
    const flagged = await screen.findAllByText(/exceeds usable roll length 100 by 35 mm/)
    expect(flagged).toHaveLength(2)
    // the whole form is preserved for correction
    expect(screen.getByTestId('segment-bundle-0')).toHaveValue('G1')
    expect(screen.getByTestId('segment-bundle-1')).toHaveValue('G1')
    expect(screen.getByTestId('segment-length-0')).toHaveValue(600)
  })
})
