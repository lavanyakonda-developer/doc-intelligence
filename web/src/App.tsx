import { useEffect, useState } from "react";
import ContractList from "./components/ContractList";
import EvidenceText from "./components/EvidenceText";
import FieldsTable from "./components/FieldsTable";
import ResultsPage from "./components/ResultsPage";
import { useContract, useEvals, useIndex } from "./data";

// Hash routes work on GitHub Pages with no server config: #/c/<key> and #/results.
type Route = { view: "contracts"; key: string | null } | { view: "results" };

function parseHash(hash: string): Route {
  const [, view, key] = hash.replace(/^#/, "").split("/");
  if (view === "results") return { view: "results" };
  return { view: "contracts", key: view === "c" && key ? key : null };
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
        <a className="brand" href="#/">docintel</a>
        <nav>
          <a href="#/" aria-current={route.view === "contracts" ? "page" : undefined}>Contracts</a>
          <a href="#/results" aria-current={route.view === "results" ? "page" : undefined}>Results</a>
          <a href="https://github.com/lavanyakonda-developer/doc-intelligence">Code</a>
        </nav>
      </header>
      <main>{route.view === "results" ? <Results /> : <Contracts selectedKey={route.key} />}</main>
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

  if (index.state !== "ready") return <Status of={index} />;
  const selected = contract.state === "ready" ? contract.data : null;
  return (
    <div className="contracts">
      <ContractList
        contracts={index.data.contracts}
        selectedKey={selectedKey}
        onSelect={(key) => (window.location.hash = `#/c/${key}`)}
      />
      {selectedKey === null ? (
        <p className="hint">Pick a contract to see its extracted fields and evidence.</p>
      ) : selected === null ? (
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
