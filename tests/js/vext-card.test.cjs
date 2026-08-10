/* Unit tests for the pure helpers in the bundled Lovelace card.
 * Run with: node --test tests/js/
 * The card is a browser file, so stub the DOM globals it touches on load.
 */
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");

globalThis.HTMLElement = class {};
globalThis.customElements = { define() {} };
globalThis.window = globalThis;

const card = require(path.join(__dirname, "../../custom_components/vext/www/vext-card.js"));
const { pct, capacity, num, clamp, WATER_MAX_L, NUTRIENT_MAX_ML } = card;

test("water tank capacity matches the Vext 2.0 hardware", () => {
  assert.strictEqual(WATER_MAX_L, 24);
  assert.strictEqual(NUTRIENT_MAX_ML, 350);
});

test("pct scales a reading against its tank size", () => {
  assert.strictEqual(pct(12, 24), 50);
  assert.strictEqual(pct(24, 24), 100);
  assert.strictEqual(pct(0, 24), 0);
});

test("a 15.7 L reading is not a full tank", () => {
  const filled = pct(15.7, WATER_MAX_L);
  assert.ok(filled > 60 && filled < 70, `expected ~65%, got ${filled}`);
  assert.notStrictEqual(filled, 100);
});

test("pct clamps out-of-range readings instead of overflowing the bar", () => {
  assert.strictEqual(pct(30, 24), 100);
  assert.strictEqual(pct(-5, 24), 0);
});

test("pct treats a missing reading as empty", () => {
  assert.strictEqual(pct(null, 24), 0);
  assert.strictEqual(pct(undefined, 24), 0);
  assert.strictEqual(pct("", 24), 0);
});

test("pct refuses a zero or bogus maximum rather than dividing by it", () => {
  assert.strictEqual(pct(10, 0), 0);
  assert.strictEqual(pct(10, -1), 0);
  assert.strictEqual(pct(10, null), 0);
  assert.strictEqual(pct(10, "abc"), 0);
});

test("capacity prefers a positive card override", () => {
  assert.strictEqual(capacity(10, WATER_MAX_L), 10);
  assert.strictEqual(capacity("18", WATER_MAX_L), 18);
});

test("capacity falls back on missing or nonsense overrides", () => {
  assert.strictEqual(capacity(undefined, WATER_MAX_L), 24);
  assert.strictEqual(capacity(null, WATER_MAX_L), 24);
  assert.strictEqual(capacity(0, WATER_MAX_L), 24);
  assert.strictEqual(capacity(-3, WATER_MAX_L), 24);
  assert.strictEqual(capacity("plenty", WATER_MAX_L), 24);
});

test("num rejects non-numeric states", () => {
  assert.strictEqual(num("15.7"), 15.7);
  assert.strictEqual(num("unavailable"), null);
  assert.strictEqual(num(null), null);
});

test("clamp bounds a value", () => {
  assert.strictEqual(clamp(5, 0, 100), 5);
  assert.strictEqual(clamp(-1, 0, 100), 0);
  assert.strictEqual(clamp(101, 0, 100), 100);
});
