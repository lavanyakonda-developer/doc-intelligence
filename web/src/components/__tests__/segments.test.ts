import { describe, expect, it } from "vitest";
import { splitSegments } from "../../segments";

const join = (s: { text: string }[]) => s.map((x) => x.text).join("");
const marked = (s: { text: string; highlighted: boolean }[]) =>
  s.filter((x) => x.highlighted).map((x) => x.text);

// Remove `.skip` when you start implementing splitSegments.
describe.skip("splitSegments", () => {
  const text = "0123456789";

  it("no spans -> one plain segment", () => {
    expect(splitSegments(text, [])).toEqual([{ text, highlighted: false }]);
  });

  it("highlights one span", () => {
    expect(splitSegments(text, [[2, 5]])).toEqual([
      { text: "01", highlighted: false },
      { text: "234", highlighted: true },
      { text: "56789", highlighted: false },
    ]);
  });

  it("merges overlapping, touching and unsorted spans", () => {
    expect(marked(splitSegments(text, [[6, 8], [1, 3], [2, 4], [4, 5]]))).toEqual(["1234", "67"]);
  });

  it("clamps out-of-range spans and drops empty ones", () => {
    expect(marked(splitSegments(text, [[-5, 2], [8, 99], [5, 5]]))).toEqual(["01", "89"]);
  });

  it("never loses or duplicates text, never emits empty segments", () => {
    const s = splitSegments(text, [[0, 10], [3, 4]]);
    expect(join(s)).toBe(text);
    expect(s.every((x) => x.text.length > 0)).toBe(true);
  });

  it("empty text -> no segments", () => {
    expect(splitSegments("", [[0, 3]])).toEqual([]);
  });
});
