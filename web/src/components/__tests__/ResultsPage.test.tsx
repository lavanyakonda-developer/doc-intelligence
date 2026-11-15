import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ResultsPage from "../ResultsPage";
import { evals } from "./fixtures";

describe("ResultsPage", () => {
  it("states the test-set size", () => {
    render(<ResultsPage evals={evals} />);
    expect(screen.getByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(screen.getByText(/22 held-out test contracts/)).toBeInTheDocument();
  });

  it("shows F1 with its confidence interval and marks production", () => {
    render(<ResultsPage evals={evals} />);
    expect(screen.getByText("84.5 [73.6, 92.2]")).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /^gpt-6-luna/ })).toHaveTextContent(/production/i);
  });

  it("signs paired deltas", () => {
    render(<ResultsPage evals={evals} />);
    expect(screen.getByText(/-0\.1/)).toBeInTheDocument();
    expect(screen.getByText(/\+1\.2/)).toBeInTheDocument();
  });

  it("per-field and parser tables", () => {
    render(<ResultsPage evals={evals} />);
    expect(screen.getByRole("row", { name: /Governing law/ })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /vision-gpt-6-luna.*heavy/ })).toHaveTextContent("0.609");
  });
});
