import { FIELD_LABELS, pct } from "../format";
import type { CI, Evals } from "../types/evals";

// The eval numbers behind the README. Every F1 carries its 95% bootstrap interval, drawn as
// a range bar, because a point estimate on 22 documents alone would overstate what we know.

const signed = (x: number) => `${x > 0 ? "+" : ""}${x.toFixed(1)}`;
const minus = (s: string) => s.replace("-", "−"); // typographic minus for display-only text
const perDoc = (x: number) => `$${x.toFixed(4)}`; // same precision on every row
const perK = (x: number) => (x === 0 ? "$0" : `$${x.toFixed(3)}`);
const ciText = (f1: number, ci: CI) => `${f1.toFixed(1)} [${ci[0].toFixed(1)}, ${ci[1].toFixed(1)}]`;

/** Point estimate + interval on a fixed scale. Decorative: the numbers are always in text. */
function RangeBar({ value, ci, domain = [0, 100], zero }: {
  value: number; ci: CI; domain?: [number, number]; zero?: boolean;
}) {
  const at = (x: number) =>
    `${((Math.min(Math.max(x, domain[0]), domain[1]) - domain[0]) / (domain[1] - domain[0])) * 100}%`;
  return (
    <span className="range" aria-hidden="true" title={`${signedOr(value, zero)} · 95% CI ${ci[0]} to ${ci[1]}`}>
      {zero && <span className="range-zero" style={{ left: at(0) }} />}
      <span className="range-ci" style={{ left: at(ci[0]), right: `calc(100% - ${at(ci[1])})` }} />
      <span className="range-dot" style={{ left: at(value) }} />
    </span>
  );
}
const signedOr = (v: number, zero?: boolean) => (zero ? minus(signed(v)) : v.toFixed(1));

/** Magnitude bar on 0–100. */
function Meter({ value }: { value: number }) {
  return (
    <span className="meter" aria-hidden="true">
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </span>
  );
}


export default function ResultsPage({ evals }: { evals: Evals }) {
  const fields = [...evals.per_field].sort((a, b) => b.f1 - a.f1);
  const e2e = new Map(evals.end_to_end_scans.map((e) => [`${e.parser}/${e.condition}`, e]));

  return (
    <section className="results">
      <header className="page-head">
        <h1>Results</h1>
        <p className="lead">
          F1 on {evals.test_docs} held-out test contracts vs CUAD lawyer labels; bars are 95%
          confidence intervals.
        </p>
      </header>


      <section className="card">
        <h2>Model comparison</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Model</th><th className="r">Run</th><th className="r">P</th><th className="r">R</th>
                <th>F1 [95% CI]</th><th className="r">$ / contract</th>
              </tr>
            </thead>
            <tbody>
              {evals.headline.map((h) => (
                <tr key={`${h.model}-${h.prompt}-${h.replicate}`} className={h.production ? "highlight" : undefined}>
                  <td>
                    {h.model}
                    {h.production && <span className="badge correct gap-left">production</span>}
                  </td>
                  <td className="num r muted">r{h.replicate}</td>
                  <td className="num r">{pct(h.precision)}</td>
                  <td className="num r">{pct(h.recall)}</td>
                  <td className="ci-cell">
                    <span className="num">{ciText(h.f1, h.ci)}</span>
                    <RangeBar value={h.f1} ci={h.ci} domain={[50, 100]} />
                  </td>
                  <td className="num r">{perDoc(h.usd_per_doc)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="caption">Scale 50–100. Overlapping intervals: the runs are not distinguishable.</p>
      </section>

      <section className="card">
        <h2>Paired comparisons</h2>
        <p className="caption">
          ΔF1 measured on the same resampled documents. An interval that crosses 0 means no
          detectable difference.
        </p>
        <ul className="paired">
          {evals.paired.map((p) => {
            const crossesZero = p.ci[0] <= 0 && p.ci[1] >= 0;
            return (
              <li key={p.label}>
                <span className="paired-label">{p.label}</span>
                <span className="paired-delta num">{signed(p.delta)}</span>
                <span className="paired-ci num muted">
                  [{minus(signed(p.ci[0]))}, {minus(signed(p.ci[1]))}]
                </span>
                <RangeBar value={p.delta} ci={p.ci} domain={[-10, 10]} zero />
                <span className={`badge ${crossesZero ? "absent" : "correct"}`}>
                  {crossesZero ? "no difference" : "significant"}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="card">
        <h2>Per field</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Field</th><th>Type</th><th className="r">P</th><th className="r">R</th>
                <th>F1</th><th className="r">TP / FP / FN</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((f) => (
                <tr key={f.field}>
                  <td>{FIELD_LABELS[f.field] ?? f.field}</td>
                  <td><span className="chip">{f.type.replace("_", " ")}</span></td>
                  <td className="num r">{pct(f.precision)}</td>
                  <td className="num r">{pct(f.recall)}</td>
                  <td className="meter-cell">
                    <span className="num">{pct(f.f1)}</span>
                    <Meter value={f.f1} />
                    {f.doc_macro_f1 !== null && (
                      <small className="muted">{pct(f.doc_macro_f1)} per contract</small>
                    )}
                  </td>
                  <td className="num r muted">{f.tp} / {f.fp} / {f.fn}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>Parsers on scanned PDFs</h2>
        <p className="caption">
          Evidence recall: share of lawyer-highlighted clauses still findable in the parsed
          text. End-to-end F1: extraction quality on top of that parser.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Parser</th><th>Scan</th><th>Evidence recall</th><th className="r">WER</th>
                <th className="r">End-to-end F1</th><th className="r">$ / 1k pages</th>
              </tr>
            </thead>
            <tbody>
              {evals.parsers.map((p) => {
                const e = e2e.get(`${p.parser}/${p.condition}`);
                return (
                  <tr key={`${p.parser}-${p.condition}`}>
                    <td>{p.parser}</td>
                    <td><span className={`chip scan-${p.condition}`}>{p.condition}</span></td>
                    <td className="meter-cell">
                      <span className="num">{pct(p.evidence_fuzzy_pct)}%</span>
                      <Meter value={p.evidence_fuzzy_pct} />
                    </td>
                    <td className="num r">{pct(p.wer_pct)}%</td>
                    <td className="num r">{e ? e.f1.toFixed(1) : <span className="muted">—</span>}</td>
                    <td className="num r">{perK(p.usd_per_1k_pages)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
