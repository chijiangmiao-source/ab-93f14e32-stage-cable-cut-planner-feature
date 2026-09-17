import type { FieldError } from './types'

/** Normalize a FastAPI/Pydantic loc array to a dotted field key,
 *  e.g. ["body", "segments", 2, "length"] -> "segments.2.length". */
export function fieldKey(loc: Array<string | number>): string {
  const parts = [...loc]
  if (parts[0] === 'body') parts.shift()
  return parts.map(String).join('.')
}

/** Group validation errors by field key, preserving server order. */
export function groupErrors(errors: FieldError[]): Map<string, string[]> {
  const grouped = new Map<string, string[]>()
  for (const err of errors) {
    const key = fieldKey(err.loc)
    const list = grouped.get(key)
    if (list) list.push(err.msg)
    else grouped.set(key, [err.msg])
  }
  return grouped
}
