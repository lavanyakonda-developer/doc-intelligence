import type { KeyboardEvent } from "react";
import { FIELD_LABELS, formatValue } from "../format";
import type { DemoContract } from "../types/api";

// One row per extracted field: value, validator verdict, and how it scored against the
// CUAD label. Rows with evidence select the field, which highlights its quote in the text.

interface Props {
  contract: DemoContract;
  selectedField: string | null;
  onSelectField: (name: string | null) => void;
}

export default function FieldsTable({ contract, selectedField, onSelectField }: Props) {
  const { result, truth } = contract;
  // The record is typed per field; for a generic table, index it by name.
  const record = result.record as unknown as Record<string, { value: unknown } | undefined>;

  return (
    <section className="fields">
      <h2>{formatValue(record.document_name?.value) || result.doc_id}</h2>
      <p className="hint">Click a row to highlight its evidence in the contract.</p>
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>Value</th>
            <th>Status</th>
            <th>vs CUAD</th>
          </tr>
        </thead>
        <tbody>
          {Object.keys(truth).map((name) => {
            const field = result.fields[name];
            const selected = name === selectedField;
            const clickable = (field?.spans.length ?? 0) > 0;
            const toggle = () => onSelectField(selected ? null : name);
            const onKey = (e: KeyboardEvent) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggle();
              }
            };
            return (
              <tr
                key={name}
                aria-selected={selected}
                className={clickable ? "clickable" : undefined}
                onClick={clickable ? toggle : undefined}
                onKeyDown={clickable ? onKey : undefined}
                tabIndex={clickable ? 0 : undefined}
              >
                <td>{FIELD_LABELS[name] ?? name}</td>
                <td>{formatValue(record[name]?.value)}</td>
                <td>
                  <span className={`badge ${field?.status ?? ""}`}>{field?.status ?? "—"}</span>
                  {field && field.status !== "verified" && field.reasons.length > 0 && (
                    <div className="reasons">{field.reasons.join("; ")}</div>
                  )}
                </td>
                <td>
                  <span className={`badge ${truth[name].outcome}`}>{truth[name].outcome}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
