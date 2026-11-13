// evals.json is plain aggregates (not a pydantic model), so its type is written by hand.
// Source: scripts/export_demo.py -> export_evals().

export type CI = [number, number]; // 95% bootstrap interval, in F1 points

export interface HeadlineRow {
  model: string;
  prompt: string;
  replicate: number;
  precision: number;
  recall: number;
  f1: number;
  ci: CI;
  usd_per_doc: number;
  production: boolean;
}

export interface FieldRow {
  field: string;
  type: string;
  precision: number;
  recall: number;
  f1: number;
  doc_macro_f1: number | null; // list fields only
  tp: number;
  fp: number;
  fn: number;
}

export interface GroupRow {
  group: string;
  docs: number;
  f1: number;
  ci: CI;
}

export interface ParserRow {
  parser: string;
  condition: "clean" | "light" | "heavy";
  docs: number;
  pages: number;
  evidence_exact_pct: number;
  evidence_fuzzy_pct: number;
  wer_pct: number;
  sec_per_page: number;
  usd_per_1k_pages: number;
  page_errors: number;
}

export interface Evals {
  test_docs: number;
  headline: HeadlineRow[];
  paired: { label: string; delta: number; ci: CI }[];
  per_field: FieldRow[];
  by_type: GroupRow[];
  by_length: GroupRow[];
  by_status: GroupRow[];
  end_to_end_scans: { parser: string; condition: string; f1: number; ci: CI }[];
  parsers: ParserRow[];
}
