import { FIELD_LABELS, pct, usd } from "../format";
import type { CI, Evals } from "../types/evals";

// The eval numbers behind the README: every F1 with its 95% bootstrap interval, because a
// point estimate on 22 documents alone would overstate what we know.

const signed = (x: number) => `${x > 0 ? "+" : ""}${x.toFixed(1)}`;
const perK = (x: number) => (x === 0 ? "$0" : `$${x.toFixed(3)}`);

function CiCell({ f1, ci }: { f1: number; ci: CI }) {
  return (
    <td className="num">
      {f1.toFixed(1)} [{ci[0].toFixed(1)}, {ci[1].toFixed(1)}]
    </td>
  );
}

export default function ResultsPage({ evals }: { evals: Evals }) {
  return (
    <section className="results">
      <h1>Results</h1>
      <p>
        F1 on {evals.test_docs} held-out test contracts. Brackets are 95% confidence intervals
        from bootstrap resampling of documents.
      </p>

      <section>
        <h2>Model comparison</h2>
        <table>
          <thead>
            <tr>
              <th>Model</th><th>Run</th><th>P</th><th>R</th><th>F1 [95% CI]</th><th>$ / doc</th>
            </tr>
          </thead>
          <tbody>
            {evals.headline.map((h) => (
              <tr key={`${h.model}-${h.prompt}-${h.replicate}`}>
                <td>
                  {h.model}
                  {h.production && <span className="badge correct"> production</span>}
                </td>
                <td className="num">r{h.replicate}</td>
                <td className="num">{pct(h.precision)}</td>
                <td className="num">{pct(h.recall)}</td>
                <CiCell f1={h.f1} ci={h.ci} />
                <td className="num">{usd(h.usd_per_doc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Paired comparisons</h2>
        <p className="hint">ΔF1 on the same resampled documents; an interval spanning 0 means no detectable difference.</p>
        <ul>
          {evals.paired.map((p) => (
            <li key={p.label}>
              {p.label}: <strong className="num">{signed(p.delta)}</strong>{" "}
              <span className="num">[{signed(p.ci[0])}, {signed(p.ci[1])}]</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Per field</h2>
        <table>
          <thead>
            <tr>
              <th>Field</th><th>Type</th><th>P</th><th>R</th><th>F1</th><th>TP / FP / FN</th>
            </tr>
          </thead>
          <tbody>
            {evals.per_field.map((f) => (
              <tr key={f.field}>
                <td>{FIELD_LABELS[f.field] ?? f.field}</td>
                <td>{f.type}</td>
                <td className="num">{pct(f.precision)}</td>
                <td className="num">{pct(f.recall)}</td>
                <td className="num">
                  {pct(f.f1)}
                  {f.doc_macro_f1 !== null && <small> ({pct(f.doc_macro_f1)} per contract)</small>}
                </td>
                <td className="num">{f.tp} / {f.fp} / {f.fn}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Parsers on scanned PDFs</h2>
        <p className="hint">Evidence recall: share of lawyer-highlighted clauses still findable in the parsed text.</p>
        <table>
          <thead>
            <tr>
              <th>Parser</th><th>Condition</th><th>Evidence recall %</th><th>WER %</th><th>$ / 1k pages</th>
            </tr>
          </thead>
          <tbody>
            {evals.parsers.map((p) => (
              <tr key={`${p.parser}-${p.condition}`}>
                <td>{p.parser}</td>
                <td>{p.condition}</td>
                <td className="num">{pct(p.evidence_fuzzy_pct)}</td>
                <td className="num">{pct(p.wer_pct)}</td>
                <td className="num">{perK(p.usd_per_1k_pages)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </section>
  );
}
