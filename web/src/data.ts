import { useEffect, useState } from "react";
import type { DemoContract, DemoIndex } from "./types/api";
import type { Evals } from "./types/evals";

// Files live in public/data/ and are served under the site's base path.
const DATA = `${import.meta.env.BASE_URL}data/`;

export type Loadable<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

/** Fetch a JSON file once per path. Ignores responses that arrive after the path changed
 *  (otherwise clicking quickly between contracts could show the wrong one). */
export function useJson<T>(path: string | null): Loadable<T> {
  const [value, setValue] = useState<Loadable<T>>({ state: "loading" });
  useEffect(() => {
    if (path === null) return;
    let current = true;
    setValue({ state: "loading" });
    fetch(DATA + path)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json() as Promise<T>;
      })
      .then((data) => current && setValue({ state: "ready", data }))
      .catch((e: Error) => current && setValue({ state: "error", message: e.message }));
    return () => {
      current = false;
    };
  }, [path]);
  return value;
}

export const useIndex = () => useJson<DemoIndex>("index.json");
export const useContract = (key: string | null) =>
  useJson<DemoContract>(key ? `contracts/${key}.json` : null);
export const useEvals = () => useJson<Evals>("evals.json");
