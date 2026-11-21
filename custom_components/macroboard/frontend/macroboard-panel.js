// Pagina "Macroboard" nella barra laterale di Home Assistant.
// Ogni Macroboard ha 2 pagine di tasti; il QR della board apre ?b=<device_id>.

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

class MacroboardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._sig = "";
  }

  set narrow(v) { this._narrow = v; }
  set panel(v) { this._panel = v; }
  set route(v) { this._route = v; }

  set hass(hass) {
    this._hass = hass;
    const sig = this._signature();
    if (sig !== this._sig) {
      // non ridisegnare mentre si sta scrivendo un nome pagina
      const active = this.shadowRoot.activeElement;
      if (active && active.tagName === "INPUT") { this._dirty = true; return; }
      this._sig = sig;
      this._render();
    }
  }

  _focus() {
    try { return new URLSearchParams(window.location.search).get("b"); } catch (e) { return null; }
  }

  _boards() {
    const h = this._hass;
    const boards = {};
    for (const [eid, st] of Object.entries(h.states)) {
      if (!eid.startsWith("select.")) continue;
      const a = st.attributes || {};
      if (!a.macroboard_device) continue;
      const id = a.macroboard_device;
      if (!boards[id]) {
        boards[id] = {
          id,
          name: a.macroboard_board || "Macroboard",
          status: a.macroboard_status || "",
          numKeys: a.macroboard_num_keys || 6,
          numKeysEntity: a.macroboard_num_keys_entity,
          orientEntity: a.macroboard_orient_entity,
          orientOffsetEntity: a.macroboard_orient_offset_entity,
          orientInvertEntity: a.macroboard_orient_invert_entity,
          currentPage: a.macroboard_current_page || 1,
          pageNames: a.macroboard_page_names || ["Luci", "Pagina 2"],
          pages: {},
        };
      }
      const p = a.macroboard_page || 1;
      (boards[id].pages[p] = boards[id].pages[p] || []).push({ eid, key: a.macroboard_key, state: st.state, options: a.options || [] });
    }
    const list = Object.values(boards);
    for (const b of list) for (const p of Object.keys(b.pages)) b.pages[p].sort((x, y) => x.key - y.key);
    list.sort((a, b) => a.name.localeCompare(b.name));
    return list;
  }

  _st(eid) { return eid ? this._hass.states[eid] : undefined; }

  _signature() {
    return (this._focus() || "") + JSON.stringify(this._boards().map((b) => [
      b.id, b.name, b.status, b.numKeys, b.currentPage, b.pageNames,
      [b.orientEntity, b.orientOffsetEntity, b.orientInvertEntity].map((e) => this._st(e)?.state),
      Object.entries(b.pages).map(([p, ks]) => [p, ks.map((k) => [k.state, k.options.length])]),
    ]));
  }

  _call(domain, service, data) {
    this._hass.callService(domain, service, data).catch((err) => {
      const m = this.shadowRoot.getElementById("msg");
      if (m) m.innerHTML = `<div class="err">${esc(err.message || err)}</div>`;
    });
  }

  _render() {
    if (!this._hass) return;
    const focus = this._focus();
    let boards = this._boards();
    const focused = focus && boards.some((b) => b.id === focus);
    if (focused) boards = boards.filter((b) => b.id === focus);

    const pageBlock = (b, p) => {
      const keys = (b.pages[p] || []).filter((k) => k.key <= b.numKeys);
      if (!keys.length) return "";
      const active = b.currentPage == p;
      return `
        <div class="page ${active ? "active" : ""}">
          <div class="page-head">
            <span class="badge">${p}</span>
            <input class="pname" data-board="${esc(b.id)}" data-page="${p}" value="${esc(b.pageNames[p - 1])}" maxlength="18" aria-label="Nome pagina ${p}">
            ${active ? `<span class="now">sul display</span>` : ""}
          </div>
          ${keys.map((k) => `
            <label class="row">
              <span class="num">${k.key}</span>
              <select data-eid="${esc(k.eid)}">
                ${k.options.map((o) => `<option ${o === k.state ? "selected" : ""}>${esc(o)}</option>`).join("")}
              </select>
            </label>`).join("")}
        </div>`;
    };

    const orientBlock = (b) => {
      const o = this._st(b.orientEntity);
      if (!o) return "";
      const off = this._st(b.orientOffsetEntity);
      const inv = this._st(b.orientInvertEntity);
      const offVal = off ? Math.round(Number(off.state)) : null;
      return `
        <div class="page orient">
          <div class="page-head"><span class="title">Orientamento display</span></div>
          <label class="row">
            <select data-eid="${esc(b.orientEntity)}">
              ${(o.attributes.options || []).map((v) => `<option ${v === o.state ? "selected" : ""}>${esc(v)}</option>`).join("")}
            </select>
          </label>
          ${off ? `
            <div class="opt">
              <span>Correzione sensore</span>
              <div class="seg" role="group" aria-label="Correzione sensore">
                ${[0, 90, 180, 270].map((v) => `<button data-num="${esc(b.orientOffsetEntity)}" data-v="${v}" class="${offVal === v ? "on" : ""}">${v}°</button>`).join("")}
              </div>
            </div>` : ""}
          ${inv ? `
            <label class="opt">
              <span>Inverti sensore</span>
              <input type="checkbox" class="sw" data-sw="${esc(b.orientInvertEntity)}" ${inv.state === "on" ? "checked" : ""}>
            </label>` : ""}
          <p class="small">Automatico usa l'accelerometro (se montato). Se il display gira dalla parte sbagliata cambia la correzione o inverti il sensore.</p>
        </div>`;
    };

    const cards = boards.map((b) => `
      <section class="card">
        <div class="card-head">
          <h2>${esc(b.name)}</h2>
          ${b.numKeysEntity ? `
            <div class="seg" role="group" aria-label="Numero tasti">
              <button data-nk="${esc(b.numKeysEntity)}" data-v="3" class="${b.numKeys == 3 ? "on" : ""}">3 tasti</button>
              <button data-nk="${esc(b.numKeysEntity)}" data-v="6" class="${b.numKeys == 6 ? "on" : ""}">6 tasti</button>
            </div>` : ""}
        </div>
        <p class="status">Ultimo evento: ${esc(b.status)}</p>
        ${Object.keys(b.pages).sort().map((p) => pageBlock(b, Number(p))).join("")}
        ${orientBlock(b)}
      </section>`).join("");

    const empty = `
      <section class="card">
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
        .hint { color: var(--secondary-text-color); margin: 4px 0 16px; font-size:14px; line-height:1.5; }
        .card { background: var(--card-background-color, #fff); border-radius: 12px; padding: 16px; margin-bottom:16px;
                box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
        .card-head { display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; }
        h2 { margin:0; font-size:18px; font-weight:500; }
        .status { margin:6px 0 10px; font-size:13px; color: var(--secondary-text-color); }
        .seg { display:flex; border:1px solid var(--divider-color,#ccc); border-radius:8px; overflow:hidden; }
        .seg button { background:none; border:0; padding:6px 10px; color: var(--primary-text-color); cursor:pointer; font-size:13px; }
        .seg button.on { background: var(--primary-color); color: var(--text-primary-color,#fff); }
        .page { border:1px solid var(--divider-color,#ccc); border-radius:10px; padding:10px 12px; margin-top:12px; }
        .page.active { border-color: var(--primary-color); }
        .page-head { display:flex; align-items:center; gap:10px; margin-bottom:4px; }
        .badge { width:24px; height:24px; border-radius:50%; display:grid; place-items:center; font-size:13px; font-weight:700;
                 background: var(--secondary-background-color,#eee); }
        .pname { flex:1; font-size:16px; font-weight:500; border:0; border-bottom:1px dashed var(--divider-color,#ccc);
                 background:transparent; color: var(--primary-text-color); padding:4px 0; }
        .now { font-size:12px; color: var(--primary-color); }
        .row { display:flex; align-items:center; gap:12px; margin:10px 0; }
        .num { flex:0 0 36px; height:36px; border-radius:8px; display:grid; place-items:center; font-weight:700;
               background: var(--primary-color); color: var(--text-primary-color, #fff); }
        select { flex:1; min-width:0; font-size:16px; padding:10px; border-radius:8px; border:1px solid var(--divider-color, #ccc);
                 background: var(--card-background-color, #fff); color: var(--primary-text-color); }
        .title { font-size:16px; font-weight:500; }
        .opt { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:10px 0; font-size:14px; }
        .sw { width:20px; height:20px; accent-color: var(--primary-color); }
        .small { font-size:12px; color: var(--secondary-text-color); margin:6px 0 0; line-height:1.4; }
        a { color: var(--primary-color); }
        .err { background:#b00020; color:#fff; padding:10px 12px; border-radius:8px; margin-bottom:12px; }
      </style>
      <header>
        <button class="menu" title="Menu">☰</button>
        <h1>Macroboard</h1>
      </header>
      <main>
        <div id="msg"></div>
        <p class="hint">Scegli cosa fa ogni tasto. Un clic sulla manopola passa da una pagina all'altra; tenendola premuta compare il QR. Tocca il nome di una pagina per rinominarla.</p>
        ${boards.length ? cards : empty}
        ${focused ? `<p><a href="/macroboard">Mostra tutte le Macroboard</a></p>` : ""}
      </main>`;

    const root = this.shadowRoot;
    root.querySelector(".menu").addEventListener("click", () =>
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true })));
    root.querySelectorAll("select").forEach((sel) =>
      sel.addEventListener("change", (e) => this._call("select", "select_option", { entity_id: sel.dataset.eid, option: e.target.value })));
    root.querySelectorAll("button[data-nk]").forEach((btn) =>
      btn.addEventListener("click", () => this._call("number", "set_value", { entity_id: btn.dataset.nk, value: Number(btn.dataset.v) })));
    root.querySelectorAll("button[data-num]").forEach((btn) =>
      btn.addEventListener("click", () => this._call("number", "set_value", { entity_id: btn.dataset.num, value: Number(btn.dataset.v) })));
    root.querySelectorAll("input[data-sw]").forEach((cb) =>
      cb.addEventListener("change", () => this._call("switch", cb.checked ? "turn_on" : "turn_off", { entity_id: cb.dataset.sw })));
    root.querySelectorAll("input.pname").forEach((inp) => {
      const save = () => {
        this._call("macroboard", "set_page_name", { device_id: inp.dataset.board, page: Number(inp.dataset.page), name: inp.value });
      };
      inp.addEventListener("change", save);
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") inp.blur(); });
      inp.addEventListener("blur", () => { if (this._dirty) { this._dirty = false; setTimeout(() => this.hass = this._hass, 0); } });
    });
  }
}

customElements.define("macroboard-panel", MacroboardPanel);
