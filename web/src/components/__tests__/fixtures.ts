import type { DemoContract, IndexItem } from "../../types/api";
import type { Evals } from "../../types/evals";

export const TEXT = "SUPPLY AGREEMENT\nmade between A Inc. and B LLC.\nGoverned by the laws of New York.";

const absent = { status: "absent", reasons: [], spans: [] as [number, number][] };
const span = (s: string): [number, number] => [TEXT.indexOf(s), TEXT.indexOf(s) + s.length];

export const contract = {
  result: {
    doc_id: "doc-1",
    filename: "supply.pdf",
    status: "ok",
    error: null,
    parser: "pypdf",
    pages: 2,
    run_id: "run",
    record: {
      doc_id: "doc-1",
      document_name: { value: "SUPPLY AGREEMENT", evidence: "SUPPLY AGREEMENT" },
      parties: { value: ["A Inc.", "B LLC"], evidence: "A Inc. and B LLC" },
      governing_law: {
        value: { country: "United States", region: "New York", raw: "laws of New York" },
        evidence: "laws of New York",
      },
      exclusivity: { value: false, evidence: null },
    },
    fields: {
      document_name: { status: "verified", reasons: [], spans: [span("SUPPLY AGREEMENT")] },
      parties: { status: "unverified", reasons: ["fewer than 2 parties"], spans: [span("A Inc. and B LLC")] },
      governing_law: { status: "verified", reasons: [], spans: [span("laws of New York")] },
      exclusivity: absent,
    },
    retried_fields: [],
    fixed_by_retry: [],
    cost: { parse_usd: 0, extract_usd: 0.002, retry_usd: 0, total: 0.002 },
    cost_usd: 0.002,
    seconds: 5,
    processed_at: "2026-11-13T00:00:00Z",
    text: TEXT,
    needs_review: ["parties"],
  },
  truth: {
    document_name: { gold: "SUPPLY AGREEMENT", outcome: "correct" },
    parties: { gold: ["A Inc.", "B LLC"], outcome: "correct" },
    governing_law: { gold: { country: "United States", region: "Delaware" }, outcome: "wrong" },
    exclusivity: { gold: null, outcome: "correct" },
  },
} as unknown as DemoContract; // partial record: only the fields the tests use

const item = (key: string, name: string, parties: string[]): IndexItem => ({
  key, doc_id: `${key}-id`, document_name: name, parties, contract_type: "supply", pages: 3,
  split: "test", parser: "pypdf", cost_usd: 0.002, verified: 10, unverified: 1, failed: 0,
  correct: 12, scored: 14,
});

export const contracts: IndexItem[] = [
  item("k1", "Supply Agreement", ["Acme Corp", "Beta LLC"]),
  item("k2", "License Agreement", ["Gamma Inc", "Delta Ltd"]),
];

export const evals: Evals = {
  test_docs: 22,
  headline: [
    { model: "gpt-6-luna", prompt: "extract_v3", replicate: 0, precision: 79.3, recall: 90.4,
      f1: 84.5, ci: [73.6, 92.2], usd_per_doc: 0.002, production: true },
    { model: "gpt-6.1-terra", prompt: "extract_v3", replicate: 0, precision: 78.8, recall: 90.9,
      f1: 84.4, ci: [73.5, 91.9], usd_per_doc: 0.019, production: false },
  ],
  paired: [{ label: "terra vs luna", delta: -0.1, ci: [-3.7, 3.5] },
           { label: "r1 vs r0", delta: 1.2, ci: [-0.9, 4.1] }],
  per_field: [{ field: "governing_law", type: "enum", precision: 100, recall: 100, f1: 100,
                doc_macro_f1: null, tp: 20, fp: 0, fn: 0 }],
  by_type: [], by_length: [], by_status: [], end_to_end_scans: [],
  parsers: [{ parser: "vision-gpt-6-luna", condition: "heavy", docs: 6, pages: 57,
              evidence_exact_pct: 81.7, evidence_fuzzy_pct: 100, wer_pct: 1.5,
              sec_per_page: 1.72, usd_per_1k_pages: 0.609, page_errors: 0 }],
};
