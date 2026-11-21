// Pagina "Macroboard" nella barra laterale di Home Assistant.
// Mostra ogni Macroboard con un menu per tasto. Il QR della board apre ?b=<device_id>.

class MacroboardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._sig = "";
    this._busy = new Set();
  }

  set narrow(v) { this._narrow = v; }
  set panel(v) { this._panel = v; }
  set route(v) { this._route = v; }

  set hass(hass) {
    this._hass = hass;
    const sig = this._signature();
    if (sig !== this._sig) {
      this._sig = sig;
      this._render();
    }
  }

  _focus() {
    try { return new URLSearchParams(window.location.search).get("b"); }
    catch (e) { return null; }
  }

  _boards() {
    const h = this._hass;
    const boards = {};
    for (const [eid, st] of Object.entries(h.states)) {
      if (!eid.startsWith("select.")) continue;
      const a = st.attributes || {};
      if (!a.macroboard_device) continue;
      const dev = a.macroboard_device;
      const d = (h.devices && h.devices[dev]) || {};
      if (!boards[dev]) boards[dev] = { id: dev, name: d.name_by_user || d.name || "Macroboard", keys: [] };
      boards[dev].keys.push({ eid, key: a.macroboard_key, state: st.state, options: a.options || [] });
    }
    const list = Object.values(boards);
    list.forEach((b) => b.keys.sort((x, y) => x.key - y.key));
    list.sort((a, b) => a.name.localeCompare(b.name));
    return list;
  }

  _signature() {
    const f = this._focus() || "";
    return f + JSON.stringify(this._boards().map((b) => [b.id, b.name, b.keys.map((k) => [k.state, k.options.length])]));
  }

  _select(eid, option) {
    this._busy.add(eid);
    this._hass
      .callService("select", "select_option", { entity_id: eid, option })
      .catch((err) => alertBox(this.shadowRoot, err.message || String(err)))
      .finally(() => { this._busy.delete(eid); });
  }

  _render() {
    if (!this._hass) return;
    const focus = this._focus();
    let boards = this._boards();
    const focused = focus && boards.some((b) => b.id === focus);
    if (focused) boards = boards.filter((b) => b.id === focus);

    const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

    const cards = boards.map((b) => `
      <section class="card">
        <h2>${esc(b.name)}</h2>
        ${b.keys.map((k) => `
          <label class="row">
            <span class="num">${k.key}</span>
            <select data-eid="${esc(k.eid)}">
              ${k.options.map((o) => `<option ${o === k.state ? "selected" : ""}>${esc(o)}</option>`).join("")}
            </select>
          </label>`).join("")}
      </section>`).join("");

    const empty = `
      <section class="card empty">
        <h2>Nessuna Macroboard trovata</h2>
        <p>Accendi la Macroboard, collegala al Wi-Fi e in <b>Impostazioni → Dispositivi e servizi</b> premi <b>Configura</b> sulla Macroboard rilevata.</p>
      </section>`;

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; min-height:100vh; background: var(--primary-background-color); color: var(--primary-text-color);
                font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif); }
        header { display:flex; align-items:center; gap:8px; height:56px; padding:0 12px;
                 background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); }
        header h1 { font-size:20px; font-weight:400; margin:0; }
        .menu { background:none; border:0; color:inherit; font-size:24px; cursor:pointer; padding:4px 8px; }
        main { max-width:560px; margin:0 auto; padding:16px; }
        .hint { color: var(--secondary-text-color); margin: 4px 0 16px; font-size:14px; }
        .card { background: var(--card-background-color, #fff); border-radius: 12px; padding: 16px; margin-bottom:16px;
                box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
        h2 { margin:0 0 12px; font-size:18px; font-weight:500; }
        .row { display:flex; align-items:center; gap:12px; margin:10px 0; }
        .num { flex:0 0 36px; height:36px; border-radius:8px; display:grid; place-items:center; font-weight:700;
               background: var(--primary-color); color: var(--text-primary-color, #fff); }
        select { flex:1; font-size:16px; padding:10px; border-radius:8px; border:1px solid var(--divider-color, #ccc);
                 background: var(--card-background-color, #fff); color: var(--primary-text-color); }
        a { color: var(--primary-color); }
        .err { background:#b00020; color:#fff; padding:10px 12px; border-radius:8px; margin-bottom:12px; }
      </style>
      <header>
        <button class="menu" title="Menu">☰</button>
        <h1>Macroboard</h1>
      </header>
      <main>
        <div id="msg"></div>
        <p class="hint">Scegli quale luce accende ogni tasto. La manopola regola la luminosità dell'ultima luce usata.</p>
        ${boards.length ? cards : empty}
        ${focused ? `<p><a href="/macroboard">Mostra tutte le Macroboard</a></p>` : ""}
      </main>`;

    this.shadowRoot.querySelector(".menu").addEventListener("click", () => {
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
    });
    this.shadowRoot.querySelectorAll("select").forEach((sel) => {
      sel.addEventListener("change", (e) => this._select(sel.dataset.eid, e.target.value));
    });
  }
}

function alertBox(root, text) {
  const m = root.getElementById("msg");
  if (m) m.innerHTML = `<div class="err">Errore: ${String(text).replace(/</g, "&lt;")}</div>`;
}

customElements.define("macroboard-panel", MacroboardPanel);
