export const MAX_SEGMENTS = 12
export const MAX_ALLOWANCE = 10000

export interface SegmentRow {
  key: number
  id: string
  length: string
  allowance: string
  /** Optional kit number as typed in the form; blank packs independently. */
  kit: string
}

let nextKey = 1

export function makeRow(
  id = '',
  length = '',
  allowance = '',
  kit = '',
): SegmentRow {
  return { key: nextKey++, id, length, allowance, kit }
}

/** Smallest "S<n>" id not currently used: S1, S2, ... */
export function nextDefaultId(rows: SegmentRow[]): string {
  const used = new Set(rows.map((r) => r.id.trim()))
  let i = 1
  while (used.has(`S${i}`)) i += 1
  return `S${i}`
}

export function addRow(rows: SegmentRow[]): SegmentRow[] {
  if (rows.length >= MAX_SEGMENTS) return rows
  return [...rows, makeRow(nextDefaultId(rows))]
}

export function removeRow(rows: SegmentRow[], key: number): SegmentRow[] {
  if (rows.length <= 1) return rows
  return rows.filter((r) => r.key !== key)
}

export function updateRow(
  rows: SegmentRow[],
  key: number,
  patch: Partial<Pick<SegmentRow, 'id' | 'length' | 'allowance' | 'kit'>>,
): SegmentRow[] {
  return rows.map((r) => (r.key === key ? { ...r, ...patch } : r))
}
