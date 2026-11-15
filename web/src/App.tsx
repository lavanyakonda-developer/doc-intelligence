import { useEffect, useState } from "react";
import ContractList from "./components/ContractList";
import EvidenceText from "./components/EvidenceText";
import FieldsTable from "./components/FieldsTable";
import ResultsPage from "./components/ResultsPage";
import { useContract, useEvals, useIndex } from "./data";

// Hash routes work on GitHub Pages with no server config: #/results (the default landing
// page), #/c (first contract) and #/c/<key>.
type Route = { view: "contracts"; key: string | null } | { view: "results" };

function parseHash(hash: string): Route {
  const [, view, key] = hash.replace(/^#/, "").split("/");
  if (view === "c") return { view: "contracts", key: key || null };
  return { view: "results" };
}

function useRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export default function App() {
  const route = useRoute();
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/results">docintel</a>
        <nav>
          <a href="#/results" aria-current={route.view === "results" ? "page" : undefined}>results</a>
          <a href="#/c" aria-current={route.view === "contracts" ? "page" : undefined}>contracts</a>
        </nav>
        <a className="code-link" href="https://github.com/lavanyakonda-developer/doc-intelligence">code</a>
      </header>
      <main className={`view-${route.view}`}>
        {route.view === "results" ? <Results /> : <Contracts selectedKey={route.key} />}
      </main>
      <footer>
        Precomputed output of the real pipeline (gpt-6-luna, prompt v3); no live model calls.
        Contracts from <a href="https://www.atticusprojectai.org/cuad">CUAD</a> by The Atticus
        Project, CC BY 4.0.
      </footer>
    </div>
  );
}

function Contracts({ selectedKey }: { selectedKey: string | null }) {
  const index = useIndex();
  const contract = useContract(selectedKey);
  // Which field's evidence is highlighted. Lives here (the common parent) because both the
  // table (sets it) and the text panel (reads it) need it: "lifting state up".
  const [field, setField] = useState<string | null>(null);
  useEffect(() => setField(null), [selectedKey]);

  // No contract in the URL: open the first one. replaceState, not a new history entry, so
  // Back doesn't bounce between #/c and #/c/<first>.
  const firstKey = index.state === "ready" ? index.data.contracts[0]?.key : undefined;
  useEffect(() => {
    if (selectedKey === null && firstKey) {
      window.history.replaceState(null, "", `#/c/${firstKey}`);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    }
  }, [selectedKey, firstKey]);

  if (index.state !== "ready") return <Status of={index} />;
  const selected = contract.state === "ready" ? contract.data : null;
  return (
    <div className="contracts">
      <ContractList
        contracts={index.data.contracts}
        selectedKey={selectedKey}
        onSelect={(key) => (window.location.hash = `#/c/${key}`)}
      />
      {selected === null ? (
        <Status of={contract} />
      ) : (
        <>
          <FieldsTable contract={selected} selectedField={field} onSelectField={setField} />
          <EvidenceText
            text={selected.result.text ?? ""}
            spans={field ? selected.result.fields[field]?.spans ?? [] : []}
          />
        </>
      )}
    </div>
  );
}

function Results() {
  const evals = useEvals();
  return evals.state === "ready" ? <ResultsPage evals={evals.data} /> : <Status of={evals} />;
}

function Status({ of }: { of: { state: string; message?: string } }) {
  return <p className="status">{of.state === "error" ? `Could not load: ${of.message}` : "Loading…"}</p>;
}
