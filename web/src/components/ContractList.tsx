import type { IndexItem } from "../types/api";

// YOUR TASK. Spec (tests: __tests__/ContractList.test.tsx):
//   - one button per contract, showing document_name (or doc_id if null), contract_type and pages
//   - show "<correct>/<scored> correct" for each contract
//   - the selected contract's button has aria-pressed="true", others "false"
//   - clicking a button calls onSelect(key)
//   - a search box (role "searchbox", label "Filter contracts") filters case-insensitively
//     by document name or any party
// Hint: keep the filter text in useState; derive the visible list while rendering (don't
// store the filtered list in state).

interface Props {
  contracts: IndexItem[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export default function ContractList({ contracts, selectedKey, onSelect }: Props) {
  void selectedKey; // remove when implemented
  return (
    <aside className="contract-list">
      {contracts.map((c) => (
        <button key={c.key} onClick={() => onSelect(c.key)}>
          {c.document_name ?? c.doc_id}
        </button>
      ))}
    </aside>
  );
}
