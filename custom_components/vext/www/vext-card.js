/*! Vext cabinet card — bundled with the Vext integration (no HACS cards needed).
 *  Usage:  type: custom:vext-cabinet-card         (shows every Vext cabinet)
 *          type: custom:vext-cabinet-card
 *          cabinet: "Vext cabinet left"            (single cabinet by device name)
 */
const GREEN = "#3C5A43";
const CREAM = "#F3EFE4";
const YELLOW = "#EFC13C";
const WATER = "#2E9BD6";
const GROW = "#6E9E76";
const BLOOM = "#E39A52";

// Tank sizes used to scale the fill bars. Vext 2.0 ships a 24 L water tank;
// the nutrient bottles are ~350 mL. Both can be overridden per card with
// `water_max_l:` / `nutrient_max_ml:` for other hardware revisions.
const WATER_MAX_L = 24;
const NUTRIENT_MAX_ML = 350;

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
// Fill percentage of a bar, tolerant of null readings and bogus maxima.
const pct = (v, max) => (num(max) === null || max <= 0 ? 0 : clamp(((num(v) ?? 0) / max) * 100, 0, 100));
// A positive override wins, otherwise the built-in capacity.
const capacity = (override, fallback) => {
  const v = num(override);
  return v !== null && v > 0 ? v : fallback;
};
const num = (v) => (v === undefined || v === null || v === "" || isNaN(Number(v)) ? null : Number(v));

function cabinetNames(hass) {
  const ents = hass?.entities || {};
  const devs = hass?.devices || {};
  const set = new Set();
  for (const e of Object.values(ents)) {
    if (e.platform === "vext" && e.device_id) {
      const d = devs[e.device_id];
      if (d) set.add(d.name_by_user || d.name);
    }
  }
  return [...set].sort();
}

class VextCabinetCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
  }

  set hass(hass) {
    this._hass = hass;
    if (document.activeElement && this.contains(document.activeElement)) return; // don't stomp a drag/typing
    this._render();
  }

  getCardSize() {
    return 12;
  }

  static getConfigElement() {
    return document.createElement("vext-cabinet-card-editor");
  }

  static getStubConfig(hass) {
    const first = cabinetNames(hass)[0];
    return first ? { cabinet: first } : {};
  }

  _cabinets() {
    const hass = this._hass;
    const ents = hass.entities || {};
    const devs = hass.devices || {};
    // group vext entities by device
    const byDev = {};
    for (const [eid, e] of Object.entries(ents)) {
      if (e.platform !== "vext" || !e.device_id) continue;
      (byDev[e.device_id] ||= []).push(eid);
    }
    let cabs = Object.entries(byDev).map(([devId, eids]) => {
      const dev = devs[devId] || {};
      const name = dev.name_by_user || dev.name || "Vext cabinet";
      const find = (suffix) => eids.find((x) => x.endsWith(suffix));
      return { devId, name, eids, find };
    });
    cabs = cabs.filter((c) => c.eids.some((e) => e.includes("_plant_health") || e.includes("_temperature")));
    if (this._config.cabinet) cabs = cabs.filter((c) => c.name === this._config.cabinet);
    cabs.sort((a, b) => a.name.localeCompare(b.name));
    return cabs;
  }

  _st(eid) {
    if (!eid) return undefined;
    const s = this._hass.states[eid];
    return s ? s.state : undefined;
  }
  _attr(eid, key) {
    if (!eid) return undefined;
    const s = this._hass.states[eid];
    return s ? s.attributes[key] : undefined;
  }

  _render() {
    if (!this._hass) return;
    const cabs = this._cabinets();
    if (!this._built) {
      this.innerHTML = `<style>${STYLES}</style><div class="vx-root"></div>`;
      this._built = true;
    }
    const root = this.querySelector(".vx-root");
    root.innerHTML = cabs.map((c) => this._cabinet(c)).join("") ||
      `<ha-card><div style="padding:16px">No Vext cabinets found.</div></ha-card>`;
    this._wire(root, cabs);
  }

  _cabinet(c) {
    const s = (suf) => this._st(c.find(suf));
    const a = (suf, k) => this._attr(c.find(suf), k);

    const score = num(s("_plant_health"));
    const scoreMsg = a("_plant_health", "message") || "";
    const temp = num(s("_temperature"));
    const hum = num(s("_humidity"));
    const water = num(s("_water"));
    const grow = num(s("_nutrient_grow"));
    const bloom = num(s("_nutrient_bloom"));
    const bright = num(s("_brightness"));
    const fogM = num(s("_fog_moisture"));
    const fogR = num(s("_fog_rhythm"));
    const lOn = s("_lights_on");
    const lOff = s("_lights_off");
    const pods = a("_pods_past_prime", "pods") || [];
    const ready = num(s("_pods_ready"));

    const waterMax = capacity(this._config?.water_max_l, WATER_MAX_L);
    const nutrientMax = capacity(this._config?.nutrient_max_ml, NUTRIENT_MAX_ML);

    const gradW = score === null ? 0 : clamp(score, 0, 100);
    const podCells = pods.map((p) => {
      const col = p.status === "PAST_PRIME" ? "#F4A6B0" : p.status === "GROWING" ? "#B8E0A0" : "#7CDA6B";
      return `<div class="vx-pod" style="border-color:${col}" title="${(p.plant || "") + " · " + (p.status || "")}">
        ${p.image ? `<img loading="lazy" src="${p.image}">` : ""}</div>`;
    }).join("");

    return `
    <ha-card class="vx-card" data-dev="${c.devId}">
      <div class="vx-head"><span class="vx-title">${c.name}</span>
        <span class="vx-badge">${score ?? "–"}</span></div>

      <div class="vx-health">
        <div class="vx-health-top"><span>Plant health</span><b>${score ?? "–"}</b></div>
        <div class="vx-bar"><div class="vx-bar-grad" style="width:${gradW}%"></div></div>
        <div class="vx-msg">${scoreMsg}</div>
      </div>

      <div class="vx-grid2">
        <div class="vx-mini"><span>🌡️ Temp</span><b>${temp === null ? "–" : temp.toFixed(1)}°C</b></div>
        <div class="vx-mini"><span>💧 Humidity</span><b>${hum === null ? "–" : Math.round(hum)}%</b></div>
      </div>

      <div class="vx-block vx-green">
        <div class="vx-block-top"><span>🚰 Water</span><b>${water === null ? "–" : water.toFixed(1)} / ${waterMax} L</b></div>
        <div class="vx-bar dark"><div style="width:${pct(water, waterMax)}%;background:${WATER}"></div></div>
      </div>

      <div class="vx-grid2">
        <div class="vx-block vx-green sm"><div class="vx-block-top"><span>Grow</span><b>${grow ?? "–"} mL</b></div>
          <div class="vx-bar dark"><div style="width:${pct(grow, nutrientMax)}%;background:${GROW}"></div></div></div>
        <div class="vx-block vx-green sm"><div class="vx-block-top"><span>Bloom</span><b>${bloom ?? "–"} mL</b></div>
          <div class="vx-bar dark"><div style="width:${pct(bloom, nutrientMax)}%;background:${BLOOM}"></div></div></div>
      </div>

      <div class="vx-podwrap"><div class="vx-podhead">Plant wall · ${ready ?? 0} ready</div>
        <div class="vx-podgrid">${podCells}</div></div>

      <div class="vx-ctl">
        <label>Brightness <b>${bright ?? "–"}%</b>
          <input type="range" min="0" max="100" step="1" value="${bright ?? 0}" data-svc="number" data-suf="_brightness"></label>
        <label>Fog moisture <b>${fogM ?? "–"}%</b>
          <input type="range" min="-45" max="45" step="15" value="${fogM ?? 0}" data-svc="number" data-suf="_fog_moisture"></label>
        <label>Fog rhythm <b>${fogR ?? "–"}%</b>
          <input type="range" min="-45" max="45" step="15" value="${fogR ?? 0}" data-svc="number" data-suf="_fog_rhythm"></label>
        <div class="vx-times">
          <label>Lights on <input type="time" value="${(lOn || "08:00:00").slice(0,5)}" data-svc="time" data-suf="_lights_on"></label>
          <label>Lights off <input type="time" value="${(lOff || "22:00:00").slice(0,5)}" data-svc="time" data-suf="_lights_off"></label>
        </div>
      </div>
    </ha-card>`;
  }

  _wire(root, cabs) {
    const byDev = Object.fromEntries(cabs.map((c) => [c.devId, c]));
    root.querySelectorAll("input[data-svc]").forEach((el) => {
      const card = el.closest(".vx-card");
      const c = byDev[card.dataset.dev];
      const suf = el.dataset.suf;
      const eid = c.find(suf);
      const svc = el.dataset.svc;
      const handler = () => {
        if (!eid) return;
        if (svc === "number") {
          this._hass.callService("number", "set_value", { entity_id: eid, value: Number(el.value) });
        } else {
          const v = el.value.length === 5 ? el.value + ":00" : el.value;
          this._hass.callService("time", "set_value", { entity_id: eid, time: v });
        }
      };
      el.addEventListener("change", handler);
    });
  }
}

const STYLES = `
.vx-root{display:flex;flex-direction:column;gap:16px}
.vx-card{background:${CREAM};border-radius:26px;padding:16px;overflow:hidden}
.vx-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.vx-title{font-size:22px;font-weight:800;color:${GREEN}}
.vx-badge{background:${GREEN};color:#fff;border-radius:16px;padding:4px 12px;font-weight:800}
.vx-health{background:${GREEN};color:#fff;border-radius:22px;padding:14px;margin-bottom:12px}
.vx-health-top{display:flex;justify-content:space-between;font-size:15px}
.vx-health-top b{font-size:30px}
.vx-msg{opacity:.85;font-size:13px;margin-top:6px}
.vx-bar{height:16px;border-radius:10px;background:#0002;overflow:hidden;margin-top:8px}
.vx-bar.dark{background:#ffffff22}
.vx-bar>div{height:100%;border-radius:10px}
.vx-bar-grad{height:100%;border-radius:10px;background:linear-gradient(90deg,#E8836F,#EFC13C,#5FBE6B)}
.vx-grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.vx-mini{background:${GREEN};color:#fff;border-radius:18px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}
.vx-mini b{font-size:22px}
.vx-block{border-radius:22px;padding:14px;margin-bottom:12px}
.vx-green{background:${GREEN};color:#fff}
.vx-block.sm{margin-bottom:0}
.vx-block-top{display:flex;justify-content:space-between;font-size:15px}
.vx-block-top b{font-size:20px}
.vx-podwrap{background:${GREEN};border-radius:22px;padding:14px;margin-bottom:12px}
.vx-podhead{color:#fff;margin-bottom:10px;font-weight:600}
.vx-podgrid{display:grid;grid-template-columns:repeat(9,1fr);gap:6px}
.vx-pod{aspect-ratio:1;border:3px solid #7CDA6B;border-radius:10px;overflow:hidden;background:#0002}
.vx-pod img{width:100%;height:100%;object-fit:cover;display:block;border-radius:7px}
.vx-ctl{display:flex;flex-direction:column;gap:10px}
.vx-ctl label{display:flex;flex-direction:column;gap:4px;color:${GREEN};font-weight:600;font-size:14px}
.vx-ctl label b{color:${GREEN}}
.vx-ctl input[type=range]{accent-color:${YELLOW}}
.vx-times{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.vx-times input{border:1px solid ${GREEN}55;border-radius:10px;padding:6px}
@media (max-width:480px){.vx-podgrid{grid-template-columns:repeat(3,1fr)}}
`;

customElements.define("vext-cabinet-card", VextCabinetCard);

class VextCabinetCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }
  set hass(hass) {
    this._hass = hass;
    this._render();
  }
  _render() {
    if (!this._hass || !this._config) return;
    const names = cabinetNames(this._hass);
    const cur = this._config.cabinet || "";
    this.innerHTML = `<div style="padding:8px 4px">
      <label style="display:block;font-weight:600;margin-bottom:6px">Cabinet</label>
      <select id="vx-c" style="width:100%;padding:10px;border-radius:10px;border:1px solid var(--divider-color,#ccc);background:var(--card-background-color,#fff);color:var(--primary-text-color,#000)">
        <option value="">All cabinets</option>
        ${names.map((n) => `<option value="${n}"${n === cur ? " selected" : ""}>${n}</option>`).join("")}
      </select>
      <div style="opacity:.6;font-size:12px;margin-top:6px">Add the card once per cabinet and pick each here.</div>
      <label style="display:block;font-weight:600;margin:14px 0 6px">Water tank size (L)</label>
      <input id="vx-w" type="number" min="1" step="0.5" placeholder="${WATER_MAX_L}" value="${this._config.water_max_l ?? ""}"
        style="width:100%;padding:10px;border-radius:10px;border:1px solid var(--divider-color,#ccc);background:var(--card-background-color,#fff);color:var(--primary-text-color,#000)">
      <div style="opacity:.6;font-size:12px;margin-top:6px">Only needed if your cabinet's tank differs from the ${WATER_MAX_L} L default.</div>
    </div>`;
    const emit = () => {
      this.dispatchEvent(
        new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true })
      );
    };
    this.querySelector("#vx-c").addEventListener("change", (e) => {
      const v = e.target.value;
      this._config = { ...this._config };
      if (v) this._config.cabinet = v;
      else delete this._config.cabinet;
      emit();
    });
    this.querySelector("#vx-w").addEventListener("change", (e) => {
      const v = num(e.target.value);
      this._config = { ...this._config };
      if (v !== null && v > 0) this._config.water_max_l = v;
      else delete this._config.water_max_l;
      emit();
    });
  }
}
customElements.define("vext-cabinet-card-editor", VextCabinetCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "vext-cabinet-card",
  name: "Vext Cabinet Card",
  description: "Vext indoor garden — health, sensors, plant wall and controls.",
  preview: true,
  documentationURL: "https://github.com/necmes/ha-vext",
});
console.info("%c VEXT-CABINET-CARD ", "background:#3C5A43;color:#fff;border-radius:4px");

// Exported for the node unit tests; harmless in the browser.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { clamp, num, pct, capacity, WATER_MAX_L, NUTRIENT_MAX_ML };
}
