import type { Evals } from "../types/evals";

// YOUR TASK. Spec (tests: __tests__/ResultsPage.test.tsx):
//   - heading "Results"; a sentence saying F1 is on `evals.test_docs` held-out test contracts
//   - "Model comparison" table from evals.headline: model, replicate, P, R, F1 with its 95% CI
//     formatted like "84.5 [73.6, 92.2]", $/doc; mark the production row
//   - "Paired comparisons" list from evals.paired: label, ΔF1 with sign ("+1.2", "-0.1") and CI
//   - "Per field" table from evals.per_field (use FIELD_LABELS)
//   - "Parsers on scanned PDFs" table from evals.parsers: parser, condition, evidence fuzzy %,
//     WER %, $/1k pages
// Hint: a small <CiCell f1 ci /> component avoids repeating the CI formatting.

interface Props {
  evals: Evals;
}

export default function ResultsPage({ evals }: Props) {
  return (
    <section className="results">
      <h1>Results</h1>
      <p>TODO: tables for {evals.test_docs} test contracts</p>
    </section>
  );
}
