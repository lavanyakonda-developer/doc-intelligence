import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only auto-unmounts between tests when vitest globals are on; we keep
// globals off (explicit imports), so unmount explicitly or renders pile up across tests.
afterEach(cleanup);
