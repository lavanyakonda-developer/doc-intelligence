import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EvidenceText from "../EvidenceText";
import { TEXT } from "./fixtures";

const law: [number, number] = [TEXT.indexOf("laws"), TEXT.indexOf("laws") + 16];

describe("EvidenceText", () => {
  it("wraps the span in <mark> and keeps all text", () => {
    const { container } = render(<EvidenceText text={TEXT} spans={[law]} />);
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(1);
    expect(marks[0]).toHaveTextContent("laws of New York");
    expect(container.textContent).toBe(TEXT);
  });

  it("no spans -> no marks", () => {
    const { container } = render(<EvidenceText text={TEXT} spans={[]} />);
    expect(container.querySelector("mark")).toBeNull();
  });

  it("scrolls the first highlight into view when spans change", () => {
    const scroll = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = scroll;
    const { rerender } = render(<EvidenceText text={TEXT} spans={[]} />);
    expect(scroll).not.toHaveBeenCalled();
    rerender(<EvidenceText text={TEXT} spans={[law]} />);
    expect(scroll).toHaveBeenCalledTimes(1);
  });
});
