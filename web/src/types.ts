export interface SegmentOut {
  id: string
  length: number
  allowance: number
  /** Bundle id when the segment was grouped; null for independent segments
   *  and for every historical record. */
  bundle: string | null
  /** ISO timestamp once this segment has actually been cut; null otherwise. */
  completed_at: string | null
}

export interface RollOut {
  position: number
  segments: SegmentOut[]
  kerf_count: number
  used_length: number
  leftover: number
  completed_count: number
}

export interface PlanOut {
  id: number
  roll_length: number
  kerf_width: number
  rolls_used: number
  total_kerf_count: number
  total_leftover: number
  completed_segment_count: number
  created_at: string
  source_plan_id: number | null
  rolls: RollOut[]
}

export interface PlanSummary {
  id: number
  roll_length: number
  kerf_width: number
  segment_count: number
  rolls_used: number
  total_kerf_count: number
  total_leftover: number
  created_at: string
  source_plan_id: number | null
}

export interface SegmentInput {
  id: string
  length: number
  allowance?: number
  /** Optional bundle id; omitted means the segment packs independently. */
  bundle?: string
}

export interface PlanCreateInput {
  roll_length: number
  kerf_width: number
  segments: SegmentInput[]
  source_plan_id?: number | null
}

export interface FieldError {
  loc: Array<string | number>
  msg: string
  type?: string
}
