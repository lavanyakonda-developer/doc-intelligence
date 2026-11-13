import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ContractList from "../ContractList";
import { contracts } from "./fixtures";

// Remove `.skip` when you start implementing ContractList.
describe.skip("ContractList", () => {
  it("shows each contract with type, pages and score", () => {
    render(<ContractList contracts={contracts} selectedKey={null} onSelect={() => {}} />);
    const first = screen.getByRole("button", { name: /Supply Agreement/ });
    expect(first).toHaveTextContent("supply");
    expect(first).toHaveTextContent("3");
    expect(first).toHaveTextContent("12/14 correct");
  });

  it("marks the selected contract and reports clicks", async () => {
    const onSelect = vi.fn();
    render(<ContractList contracts={contracts} selectedKey="k2" onSelect={onSelect} />);
    expect(screen.getByRole("button", { name: /License/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Supply/ })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(screen.getByRole("button", { name: /Supply/ }));
    expect(onSelect).toHaveBeenCalledWith("k1");
  });

  it("filters by name or party, case-insensitively", async () => {
    render(<ContractList contracts={contracts} selectedKey={null} onSelect={() => {}} />);
    const box = screen.getByRole("searchbox", { name: "Filter contracts" });
    await userEvent.type(box, "delta");
    expect(screen.queryByRole("button", { name: /Supply/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /License/ })).toBeInTheDocument();
    await userEvent.clear(box);
    await userEvent.type(box, "SUPPLY");
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });
});
