import type { DemoContract } from "../types/api";

// YOUR TASK. Spec (tests: __tests__/FieldsTable.test.tsx):
//   - a table with one row per field, in the order of contract.truth's keys;
//     columns: Field (FIELD_LABELS from ../format), Value (formatValue), Status, vs CUAD
//   - Status shows fields[name].status (verified / unverified / failed / absent)
//   - "vs CUAD" shows truth[name].outcome (correct / partial / wrong / excluded)
//   - rows with evidence spans are clickable: clicking calls onSelectField(name);
//     clicking the selected row again calls onSelectField(null)
//   - the selected row has aria-selected="true"
//   - rows WITHOUT spans are not clickable (absent fields have nothing to highlight)
//   - show the validator's reasons (fields[name].reasons) for unverified/failed fields
// Hint: getting the value: contract.result.record[name].value — the record is typed per
// field, so index it as `(record as unknown as Record<string, {value: unknown}>)[name]`.

interface Props {
  contract: DemoContract;
  selectedField: string | null;
  onSelectField: (name: string | null) => void;
}

export default function FieldsTable({ contract, selectedField, onSelectField }: Props) {
  void selectedField;
  void onSelectField;
  return (
    <section className="fields">
      <h2>{contract.result.record?.document_name.value ?? contract.result.doc_id}</h2>
      <p>TODO: fields table</p>
    </section>
  );
}
