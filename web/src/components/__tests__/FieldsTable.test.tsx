import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import FieldsTable from "../FieldsTable";
import { contract } from "./fixtures";

const row = (label: RegExp) => screen.getByRole("row", { name: label });

// Remove `.skip` when you start implementing FieldsTable.
describe.skip("FieldsTable", () => {
  it("one row per field with label, formatted value, status and CUAD outcome", () => {
    render(<FieldsTable contract={contract} selectedField={null} onSelectField={() => {}} />);
    expect(screen.getAllByRole("row")).toHaveLength(1 + 4); // header + fields
    const law = row(/Governing law/);
    expect(law).toHaveTextContent("New York, United States");
    expect(law).toHaveTextContent("verified");
    expect(law).toHaveTextContent("wrong");
  });

  it("shows validator reasons for unverified fields", () => {
    render(<FieldsTable contract={contract} selectedField={null} onSelectField={() => {}} />);
    expect(row(/Parties/)).toHaveTextContent("fewer than 2 parties");
  });

  it("selects and deselects rows that have evidence", async () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <FieldsTable contract={contract} selectedField={null} onSelectField={onSelect} />,
    );
    await userEvent.click(row(/Governing law/));
    expect(onSelect).toHaveBeenLastCalledWith("governing_law");
    rerender(<FieldsTable contract={contract} selectedField="governing_law" onSelectField={onSelect} />);
    expect(row(/Governing law/)).toHaveAttribute("aria-selected", "true");
    await userEvent.click(row(/Governing law/));
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it("rows without evidence are not clickable", async () => {
    const onSelect = vi.fn();
    render(<FieldsTable contract={contract} selectedField={null} onSelectField={onSelect} />);
    await userEvent.click(within(row(/Exclusivity/)).getAllByRole("cell")[0]);
    expect(onSelect).not.toHaveBeenCalled();
  });
});
