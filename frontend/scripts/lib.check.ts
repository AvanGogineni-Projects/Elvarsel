// Assert-based check for pure helpers (no test runner in the frontend):
//   npm run check
import assert from "node:assert/strict";
import { cheapestWindow } from "../src/lib.ts";

const at = (h: number, price: number) => ({ time: new Date(Date.UTC(2026, 10, 9, h)).toISOString(), price_eur_mwh: price });

// Cheapest 3 back-to-back hours is 02..05 (avg 2), not the lone cheaper hour 0.
const w = cheapestWindow([at(0, 1), at(1, 9), at(2, 2), at(3, 2), at(4, 2), at(5, 9)]);
assert.equal(w?.start, at(2, 0).time);
assert.equal(w?.last, at(4, 0).time);
assert.equal(w?.end, at(5, 0).time);
assert.equal(w?.avg, 2);

// A missing hour breaks the run: hours 1, 2, 4 are not contiguous.
assert.equal(cheapestWindow([at(1, 0), at(2, 0), at(4, 0)]), null);
assert.equal(cheapestWindow([at(0, 1), at(1, 1)]), null); // fewer than 3 hours
console.log("lib checks passed");
