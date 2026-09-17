import { describe, expect, it } from 'vitest'
import {
  MAX_SEGMENTS,
  addRow,
  makeRow,
  nextDefaultId,
  removeRow,
  updateRow,
} from '../segmentRows'

describe('nextDefaultId', () => {
  it('picks the smallest unused S<n> id', () => {
    expect(nextDefaultId([])).toBe('S1')
    expect(nextDefaultId([makeRow('S1'), makeRow('S2')])).toBe('S3')
    expect(nextDefaultId([makeRow('S1'), makeRow('S3')])).toBe('S2')
  })
})

describe('addRow', () => {
  it('appends a row with a fresh default id', () => {
    const rows = addRow([makeRow('S1', '100')])
    expect(rows).toHaveLength(2)
    expect(rows[1].id).toBe('S2')
  })

  it('never exceeds MAX_SEGMENTS rows', () => {
    let rows = [makeRow('S1')]
    for (let i = 0; i < MAX_SEGMENTS + 3; i += 1) rows = addRow(rows)
    expect(rows).toHaveLength(MAX_SEGMENTS)
  })
})

describe('removeRow', () => {
  it('removes the row with the given key', () => {
    const a = makeRow('S1')
    const b = makeRow('S2')
    const rows = removeRow([a, b], a.key)
    expect(rows).toEqual([b])
  })

  it('keeps at least one row', () => {
    const a = makeRow('S1')
    expect(removeRow([a], a.key)).toEqual([a])
  })
})

describe('updateRow', () => {
  it('patches only the targeted row', () => {
    const a = makeRow('S1', '100')
    const b = makeRow('S2', '200')
    const rows = updateRow([a, b], b.key, { length: '250' })
    expect(rows[0]).toEqual(a)
    expect(rows[1].length).toBe('250')
    expect(rows[1].id).toBe('S2')
  })

  it('patches the allowance field', () => {
    const a = makeRow('S1', '100')
    const rows = updateRow([a], a.key, { allowance: '50' })
    expect(rows[0].allowance).toBe('50')
    expect(rows[0].length).toBe('100')
  })
})

describe('makeRow', () => {
  it('defaults the allowance to blank (treated as zero)', () => {
    expect(makeRow('S1', '100').allowance).toBe('')
    expect(makeRow('S1', '100', '25').allowance).toBe('25')
  })

  it('defaults the kit number to blank (treated as ungrouped)', () => {
    expect(makeRow('S1', '100').kit).toBe('')
    expect(makeRow('S1', '100', '', '3').kit).toBe('3')
  })
})

describe('kit numbers', () => {
  it('updateRow patches only the kit field', () => {
    const a = makeRow('S1', '100')
    const rows = updateRow([a], a.key, { kit: '2' })
    expect(rows[0].kit).toBe('2')
    expect(rows[0].id).toBe('S1')
    expect(rows[0].length).toBe('100')
  })

  it('add/remove rows keep the kit value of untouched rows', () => {
    const a = makeRow('S1', '100', '', '5')
    const rows = addRow([a])
    expect(rows[0].kit).toBe('5')
    expect(rows[1].kit).toBe('')
    const removed = removeRow(rows, rows[1].key)
    expect(removed).toEqual([a])
  })
})
