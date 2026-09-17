export interface SegmentOut {
  id: string
  length: number
  allowance: number
  /** Kit number kept beside the cutting order; null/absent for segments
   *  packed independently and for historical plans. */
  kit_no?: number | null
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
  /** Omitted for an independent segment; segments sharing a number are
   *  solved as one indivisible kit on a single roll. */
  kit_no?: number | null
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
