import { describe, expect, it } from 'vitest'
import { fieldKey, groupErrors } from '../errors'
import type { FieldError } from '../types'

describe('fieldKey', () => {
  it('strips the FastAPI "body" prefix', () => {
    expect(fieldKey(['body', 'roll_length'])).toBe('roll_length')
  })

  it('maps segment locations to dotted keys', () => {
    expect(fieldKey(['body', 'segments', 2, 'length'])).toBe('segments.2.length')
    expect(fieldKey(['segments', 0, 'id'])).toBe('segments.0.id')
  })
})

describe('groupErrors', () => {
  it('groups messages by field key preserving order', () => {
    const errors: FieldError[] = [
      { loc: ['segments', 1, 'id'], msg: "duplicate segment id 'A'" },
      { loc: ['body', 'roll_length'], msg: 'Input should be greater than or equal to 1' },
      { loc: ['segments', 1, 'id'], msg: 'second problem' },
    ]
    const grouped = groupErrors(errors)
    expect(grouped.get('segments.1.id')).toEqual([
      "duplicate segment id 'A'",
      'second problem',
    ])
    expect(grouped.get('roll_length')).toEqual([
      'Input should be greater than or equal to 1',
    ])
  })
})
