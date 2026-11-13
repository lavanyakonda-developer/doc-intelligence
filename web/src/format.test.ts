import { describe, expect, it } from "vitest";
import { formatValue } from "./format";

describe("formatValue", () => {
  it.each([
    [null, "—"],
    [false, "—"],
    [true, "Yes"],
    ["perpetual", "Perpetual"],
    [["A Inc.", "B LLC"], "A Inc.; B LLC"],
    [{ year: 2019, month: 11, day: 12 }, "Nov 12, 2019"],
    [{ year: 2019, month: 9, day: null }, "Sep 2019"],
    [{ year: 2019, month: null, day: null }, "2019"],
    [{ value: 1, unit: "year" }, "1 year"],
    [{ value: 30, unit: "business_day" }, "30 business days"],
    [{ country: "United States", region: "New York", raw: "laws of NY" }, "New York, United States"],
    [{ country: "OTHER", region: null, raw: "where the restaurant is" }, "where the restaurant is"],
  ])("%j -> %s", (value, expected) => {
    expect(formatValue(value)).toBe(expected);
  });
});
