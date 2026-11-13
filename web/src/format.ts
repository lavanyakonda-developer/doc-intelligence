// Display helpers shared by the components. Field values have different shapes per type
// (string, list, PartialDate, Duration, Jurisdiction, boolean), so formatting lives here once.

export const FIELD_LABELS: Record<string, string> = {
  document_name: "Document name",
  parties: "Parties",
  agreement_date: "Agreement date",
  effective_date: "Effective date",
  expiration_date: "Expiration date",
  renewal_term: "Renewal term",
  notice_period_to_terminate_renewal: "Notice to terminate renewal",
  governing_law: "Governing law",
  non_compete: "Non-compete",
  exclusivity: "Exclusivity",
  uncapped_liability: "Uncapped liability",
  termination_for_convenience: "Termination for convenience",
  change_of_control: "Change of control",
  cap_on_liability: "Cap on liability",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === false) return "—";
  if (value === true) return "Yes";
  if (value === "perpetual") return "Perpetual";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join("; ") : "—";
  if (isObj(value)) {
    if ("year" in value) {
      const { year, month, day } = value as { year: number; month?: number | null; day?: number | null };
      if (!month) return String(year);
      return day ? `${MONTHS[month - 1]} ${day}, ${year}` : `${MONTHS[month - 1]} ${year}`;
    }
    if ("unit" in value) {
      const { value: n, unit } = value as { value: number; unit: string };
      const word = unit.replace("_", " ");
      return `${n} ${word}${n === 1 ? "" : "s"}`;
    }
    if ("country" in value) {
      const { country, region, raw } = value as { country: string; region?: string | null; raw?: string | null };
      if (country === "OTHER") return raw ?? "Other";
      return region ? `${region}, ${country}` : country;
    }
  }
  return JSON.stringify(value);
}

export const pct = (x: number | null | undefined) => (x === null || x === undefined ? "—" : x.toFixed(1));
export const usd = (x: number) => `$${x < 0.01 ? x.toFixed(4) : x.toFixed(2)}`;
