import { useState } from "react";
import type { IndexItem } from "../types/api";

// Sidebar: searchable list of the golden-set contracts with their score vs CUAD.
// The filter text is the only state; the visible list is derived while rendering, so it
// can never go stale relative to `contracts`.

interface Props {
  contracts: IndexItem[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export default function ContractList({ contracts, selectedKey, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const visible = needle
    ? contracts.filter((c) =>
        [c.document_name ?? "", ...c.parties].some((s) => s.toLowerCase().includes(needle)),
      )
    : contracts;

  return (
    <aside className="contract-list">
      <input
        type="search"
        aria-label="Filter contracts"
        placeholder="Filter by name or party"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {visible.map((c) => (
        <button
          key={c.key}
          aria-pressed={c.key === selectedKey}
          onClick={() => onSelect(c.key)}
        >
          <span className="item-title">{c.document_name ?? c.doc_id}</span>
          <span className="item-meta">
            {c.contract_type} · {c.pages} pages ·{" "}
            <span className={c.correct === c.scored ? "correct" : undefined}>
              {c.correct}/{c.scored} correct
            </span>
          </span>
        </button>
      ))}
      {visible.length === 0 && <p className="hint">No contracts match “{query}”.</p>}
    </aside>
  );
}
