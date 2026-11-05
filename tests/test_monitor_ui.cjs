/* Run: node tests/test_monitor_ui.cjs. Requires Playwright and Chromium.
 * Optional: AMIT_PLAYWRIGHT_MODULE, AMIT_CHROME_PATH, AMIT_SCREENSHOT_DIR.
 * Uses a fake HA connection only; no HTTP requests, UDP, or real PLCs.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require(process.env.AMIT_PLAYWRIGHT_MODULE || "playwright");

async function mount(browser, options = {}) {
  const page = await browser.newPage({ viewport: { width: 1024, height: 1000 } });
  const errors = [], requests = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.route("**/*", route => { requests.push(route.request().url()); return route.abort(); });
  await page.setContent('<!doctype html><html><head><meta charset="UTF-8"><style>body{margin:0}amit-monitor-panel{height:auto;min-height:100vh}</style></head><body></body></html>');
  await page.evaluate(() => {
    window.fakeHidden = false;
    Object.defineProperty(document, "hidden", { configurable: true, get: () => window.fakeHidden });
    customElements.define("ha-icon", class extends HTMLElement {
      connectedCallback() { this.textContent = this.getAttribute("icon") === "mdi:menu" ? "☰" : "↻"; }
    });
  });
  await page.addScriptTag({ type: "module", content: await fs.readFile(path.join(__dirname, "../custom_components/amit/frontend/monitor.js"), "utf8") });
  await page.waitForFunction(() => customElements.get("amit-monitor-panel"));
  await page.evaluate(options => {
    const variables = [
      { wid: 4101, name: "TE_obyvak", type: "Float", unit: "°C", revision: 1, readable: true },
      { wid: 4102, name: "TE_venkovni", type: "Float", unit: "°C", revision: 2, readable: true },
      { wid: 4201, name: "Zad_UT1", type: "Float", unit: "°C", revision: 3, readable: true },
      { wid: 4301, name: "Zap_cerpadlo", type: "Int", unit: null, revision: 4, readable: true },
      { wid: 4401, name: "Provozni_hodiny", type: "Long", unit: null, revision: 5, readable: true },
      { wid: 4501, name: "Program_tydne", type: "Matrix Integer", unit: null, revision: 6, readable: false },
      { wid: 0, name: '<img src="bad" onerror="window.injected=true">', type: "Int", unit: null, revision: 7, readable: true },
    ];
    const fixture = window.fixture = {
      sequence: 10, variables, entityMetadata: new Map(), active: new Map(), pending: [], nextId: 1, calls: 0,
      entries: [{ entry_id: "first", title: "Vytápění · Biosuntec" }, { entry_id: "second", title: "Vzduchotechnika · Generic" }],
      listeners: new Map(), deferSubscription: Boolean(options.deferSubscription),
      messages: [], subscriptionMessages: [], additionStatus: "pending", runtimeSuffix: "", deferPreview: false, deferConfirm: false,
    };
    if (options.matrix) Object.assign(variables[5], {
      type: "Matrix Integer", matrix_readable: true, rows: 12, cols: 8,
    });
    if (options.identification) fixture.entries[0].identification = {
      system: ["AMiT", "AMiDemo2-X - NOS999 - CIP Test", "V1.20 - V3.40 - V5.60"],
      application: ['<img src="invalid" onerror="window.injected=true">', "", "Build 1"],
    };
    fixture.reading = (wid, value, status = "ok") => ({
      wid, value, status, sequence: ++fixture.sequence,
      revision: fixture.variables.find(v => v.wid === wid)?.revision,
      timestamp: new Date(Date.now() - 60000 + fixture.sequence * 1000).toISOString(),
    });
    fixture.snapshot = (entry, options = {}) => ({ kind: "snapshot", runtime_id: `runtime-${entry}${fixture.runtimeSuffix}`, sequence: fixture.sequence,
      variables: fixture.variables.map(v => ({ ...v, configured: false, entities: [], ...fixture.entityMetadata.get(entry)?.get(v.wid) })), scan_interval: 30,
      samples: [{ ...fixture.reading(4101, 22.4), sequence: fixture.sequence }],
      intervals: Object.fromEntries(fixture.variables.filter(v => v.readable).map(v => [v.wid,
        options.interval && (!options.wids || options.wids.includes(v.wid)) ? options.interval : 30])),
    });
    fixture.connection = {
      connected: true,
      addEventListener(name, cb) { if (!fixture.listeners.has(name)) fixture.listeners.set(name, new Set()); fixture.listeners.get(name).add(cb); },
      removeEventListener(name, cb) { fixture.listeners.get(name)?.delete(cb); },
      async sendMessagePromise(message) {
        fixture.messages.push(structuredClone(message));
        if (message.type === "amit/monitor/list") return fixture.entries;
        if (message.type === "amit/monitor/read_matrix") {
          if (fixture.deferMatrix) await new Promise(resolve => { fixture.resolveMatrix = resolve; });
          if (fixture.matrixError) throw fixture.matrixError;
          return fixture.matrixResult || { ...message, timestamp: new Date().toISOString(),
            values: Array.from({ length: message.rows }, (_, row) => Array.from({ length: message.cols }, (_, col) =>
              row === 0 && col === 1 ? null : (message.row + row) * 100 + message.col + col)) };
        }
        if (message.type === "amit/monitor/preview_add") {
          if (fixture.deferPreview) await new Promise(resolve => { fixture.resolvePreview = resolve; });
          const requested = message.variables.map(v => v.wid);
          return fixture.preview || { preview_id: "synthetic-preview", expires_at: Math.floor(Date.now() / 1000) + 300,
            entry_id: message.entry_id, runtime_id: message.runtime_id, requested_wids: requested, added_wids: requested,
            already_configured_wids: [], newly_monitored_wids: requested, removed_write_wids: [], selection_mode: "explicit",
            requires_reload: true, variables: fixture.snapshot(message.entry_id).variables.filter(v => requested.includes(v.wid)) };
        }
        if (message.type === "amit/monitor/confirm_add") {
          if (fixture.deferConfirm) await new Promise(resolve => { fixture.resolveConfirm = resolve; });
          if (fixture.confirmError) throw fixture.confirmError;
          return { entry_id: message.entry_id, operation_id: "synthetic-operation", status: "saved", saved: true, error: null };
        }
        if (message.type === "amit/monitor/addition_status") {
          if (fixture.statusError) throw fixture.statusError;
          if (fixture.additionStatus === "loaded") fixture.runtimeSuffix = "-reloaded";
          return { entry_id: message.entry_id, operation_id: message.operation_id,
            status: fixture.additionStatus, saved: true, error: fixture.additionStatus === "failed" ? "reload_failed" : null };
        }
        throw Error(`Unexpected command ${message.type}`);
      },
      subscribeMessage(callback, message, opts) {
        assertType(message.type, "amit/monitor/subscribe");
        if (opts.resubscribe !== false) throw Error("Duplicate reconnect ownership");
        fixture.calls++;
        fixture.subscriptionMessages.push(structuredClone(message));
        if (fixture.subscriptionError) return Promise.reject(fixture.subscriptionError);
        if (message.interval !== undefined && (typeof message.interval !== "number" ||
            !Number.isFinite(message.interval) || message.interval < 1 || message.interval > 120))
          return Promise.reject({ code: "invalid_request" });
        if (message.wids !== undefined && (!Array.isArray(message.wids) || message.wids.some(wid =>
          !Number.isInteger(wid) || !fixture.variables.some(v => v.wid === wid && v.readable))))
          return Promise.reject({ code: "invalid_request" });
        if (fixture.rejectSelected && message.wids) return Promise.reject({ code: "invalid_request" });
        const id = fixture.nextId++;
        fixture.active.set(id, { callback, entry: message.entry_id });
        fixture.oldCallback = callback;
        if (fixture.deferSnapshot) setTimeout(() => callback(fixture.snapshot(message.entry_id, message)), 0);
        else callback(fixture.snapshot(message.entry_id, message));
        const unsubscribe = () => { fixture.active.delete(id); };
        return fixture.deferSubscription ? new Promise(resolve => fixture.pending.push(() => resolve(unsubscribe))) : Promise.resolve(unsubscribe);
      },
    };
    function assertType(actual, expected) { if (actual !== expected) throw Error(`Unexpected command ${actual}`); }
    fixture.emit = sample => { for (const active of fixture.active.values()) active.callback({ kind: "sample", runtime_id: `runtime-${active.entry}${fixture.runtimeSuffix}`, sample }); };
    fixture.metadata = (variables, entry = "first") => {
      if (!fixture.entityMetadata.has(entry)) fixture.entityMetadata.set(entry, new Map());
      for (const variable of variables) fixture.entityMetadata.get(entry).set(variable.wid, variable);
      for (const active of fixture.active.values()) if (active.entry === entry)
        active.callback({ kind: "entity_metadata", runtime_id: `runtime-${entry}${fixture.runtimeSuffix}`, variables });
    };
    fixture.event = name => { for (const cb of fixture.listeners.get(name) || []) cb(); };
    fixture.visibility = hidden => { window.fakeHidden = hidden; document.dispatchEvent(new Event("visibilitychange")); };
    window.panel = document.createElement("amit-monitor-panel");
    panel.hass = { language: "cs", config: { time_zone: "Europe/Prague" }, connection: fixture.connection };
    document.body.append(panel);
  }, options);
  await page.waitForFunction(() => panel.model.catalog.size === 7);
  await page.locator("amit-monitor-panel tbody tr").first().waitFor();
  return { page, errors, requests };
}

async function select(page, name) {
  await page.getByRole("checkbox", { name: `Vybráno: ${name}`, exact: true }).check();
  await page.waitForFunction(name => [...panel.model.selected.keys()].some(wid => panel._variableName(panel.model.catalog.get(wid)) === name), name);
}

async function theme(page, dark) {
  await page.emulateMedia({ colorScheme: dark ? "dark" : "light" });
  await page.evaluate(dark => {
    const colors = dark ? ["#111923", "#1c2733", "#e5eef5", "#a8bac8", "#344454", "#76d7fa", "#ffadb7"] :
      ["#f5f7fa", "#ffffff", "#182b3a", "#526775", "#dce4eb", "#007eaa", "#a12836"];
    ["--primary-background-color", "--card-background-color", "--primary-text-color", "--secondary-text-color", "--divider-color", "--primary-color", "--error-color"].forEach((key, i) => document.documentElement.style.setProperty(key, colors[i]));
  }, dark);
}

async function run() {
  const browser = await chromium.launch({ headless: true, ...(process.env.AMIT_CHROME_PATH ? { executablePath: process.env.AMIT_CHROME_PATH } : {}) });
  const results = [];
  try {
    {
      const { page, errors, requests } = await mount(browser, { identification: true });
      const header = page.locator(".identification");
      await header.getByText("Kontrolér:", { exact: false }).waitFor();
      assert.match(await header.textContent(), /AMiDemo2-X.*NOS999.*CIP Test.*V1.20.*V3.40.*V5.60/);
      assert.match(await header.textContent(), /<img src=/);
      for (const dark of [false, true]) {
        await theme(page, dark);
        await page.setViewportSize({ width: 390, height: 844 });
        await page.waitForTimeout(150);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        if (process.env.AMIT_SCREENSHOT_DIR) await page.screenshot({
          path: path.join(process.env.AMIT_SCREENSHOT_DIR, `identification-mobile-${dark ? "dark" : "light"}.png`), fullPage: true,
        });
      }
      await page.evaluate(() => { panel.hass = { ...panel._hass, language: "en" }; });
      await header.getByText("Controller:", { exact: false }).waitFor();
      await page.getByRole("combobox", { name: "PLC", exact: true }).selectOption("second");
      await page.waitForFunction(() => panel.shadowRoot.querySelector(".identification").hidden);
      assert.equal(await header.textContent(), "");
      assert.equal(await page.evaluate(() => fixture.messages.some(m => /identification/.test(m.type))), false);
      assert.equal(await page.evaluate(() => window.injected), undefined);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("identification header includes system/application text, safe rendering, entry isolation, languages and mobile themes without PLC requests");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser, { matrix: true });
      const dialog = page.locator(".matrix-dialog");
      const expectedTypes = ["all", "Float", "Int", "Long", "Matrix Integer", "Matrix Long", "Matrix Float", "Unknown"];
      assert.deepEqual(await page.locator(".filter option").evaluateAll(options => options.map(option => option.value)), expectedTypes);
      assert.deepEqual(await page.locator(".filter option").allTextContents(), ["Všechny typy", ...expectedTypes.slice(1)]);
      assert.equal(await page.evaluate(() => fixture.messages.filter(m => m.type === "amit/monitor/read_matrix").length), 0);
      await select(page, "TE_obyvak");
      const history = await page.evaluate(() => JSON.stringify([...panel.model.selected]));
      await page.getByRole("button", { name: "Otevřít matici", exact: true }).click();
      await dialog.locator("tbody tr").first().waitFor();
      assert.equal(await dialog.locator("tbody tr").count(), 10);
      assert.equal(await dialog.locator("tbody tr").first().locator("td").count(), 6);
      assert.equal(await dialog.locator("tbody tr").first().locator("td").nth(1).textContent(), "—");
      assert.match(await dialog.locator(".matrix-status").textContent(), /Poslední odečet/);
      assert.equal(await page.evaluate(() => JSON.stringify([...panel.model.selected])), history);
      await page.waitForTimeout(1100);
      assert.equal(await page.evaluate(() => fixture.messages.filter(m => m.type === "amit/monitor/read_matrix").length), 1);
      await dialog.getByRole("group", { name: "Řádky", exact: true }).getByRole("button", { name: "Další strana", exact: true }).click();
      await page.waitForFunction(() => panel._matrix.result?.row === 10);
      assert.equal(await dialog.locator("tbody tr").count(), 2);
      await dialog.getByRole("group", { name: "Sloupce", exact: true }).getByRole("button", { name: "Další strana", exact: true }).click();
      await page.waitForFunction(() => panel._matrix.result?.col === 6);
      assert.equal(await dialog.locator("tbody tr").first().locator("td").count(), 2);
      assert.equal(await dialog.locator("tbody tr").first().locator("td").first().textContent(), "1 006");
      await page.evaluate(() => { fixture.matrixError = { code: "busy" }; });
      await dialog.getByRole("button", { name: "Obnovit výřez", exact: true }).click();
      await page.waitForFunction(() => panel._matrix.error === "matrixBusy");
      assert.equal(await dialog.locator("tbody tr").count(), 0);
      await page.evaluate(() => { fixture.matrixError = null; });
      await dialog.getByRole("button", { name: "Obnovit výřez", exact: true }).click();
      await page.waitForFunction(() => Boolean(panel._matrix.result));
      await dialog.getByRole("group", { name: "Řádky", exact: true }).getByRole("button", { name: "Předchozí strana", exact: true }).click();
      await page.waitForFunction(() => panel._matrix.result?.row === 0);
      await dialog.getByRole("group", { name: "Sloupce", exact: true }).getByRole("button", { name: "Předchozí strana", exact: true }).click();
      await page.waitForFunction(() => panel._matrix.result?.col === 0);
      for (const dark of [false, true]) {
        await theme(page, dark);
        for (const width of [1024, 390, 320]) {
          await page.setViewportSize({ width, height: 844 });
          await page.waitForTimeout(150);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
          assert.equal(await dialog.evaluate(element => element.getBoundingClientRect().width <= innerWidth), true);
          if (process.env.AMIT_SCREENSHOT_DIR && width === 390) await page.screenshot({
            path: path.join(process.env.AMIT_SCREENSHOT_DIR, `matrix-mobile-${dark ? "dark" : "light"}.png`), fullPage: true,
          });
        }
      }
      await page.evaluate(() => { panel.hass = { ...panel._hass, language: "en" }; });
      await dialog.getByRole("button", { name: "Refresh window", exact: true }).waitFor();
      assert.deepEqual(await page.locator(".filter option").evaluateAll(options => options.map(option => option.value)), expectedTypes);
      assert.deepEqual(await page.locator(".filter option").allTextContents(), ["All types", ...expectedTypes.slice(1)]);
      await page.keyboard.press("Escape");
      await page.waitForFunction(() => panel._matrix === null);
      await page.getByRole("combobox", { name: "Variable type", exact: true }).selectOption("Matrix Integer");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll(".columns tbody tr").length === 1);
      assert.equal(await page.locator(".columns tbody tr").count(), 1);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("matrix bounded windows, row/column pages, manual refresh, busy retry, null cells, scalar history, languages and mobile themes");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser, { matrix: true });
      const dialog = page.locator(".matrix-dialog");
      await page.evaluate(() => { fixture.deferMatrix = true; });
      await page.getByRole("button", { name: "Otevřít matici", exact: true }).click();
      await page.waitForFunction(() => Boolean(fixture.resolveMatrix));
      await page.evaluate(() => {
        fixture.oldMatrix = fixture.resolveMatrix;
        fixture.variables[5].revision++;
        for (const active of fixture.active.values()) active.callback({ ...fixture.snapshot(active.entry), kind: "catalog" });
      });
      await page.waitForFunction(() => panel._matrix.stale);
      await page.evaluate(() => fixture.oldMatrix());
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => panel._matrix.result), null);
      assert.equal(await dialog.getByRole("button", { name: "Obnovit výřez", exact: true }).isDisabled(), true);
      await dialog.getByRole("button", { name: "Zavřít", exact: true }).click();
      await page.evaluate(() => { fixture.deferMatrix = false; fixture.matrixError = { code: "read_error" }; });
      await page.getByRole("button", { name: "Otevřít matici", exact: true }).click();
      await page.waitForFunction(() => panel._matrix.error === "matrixError");
      await page.evaluate(() => { fixture.matrixError = null; fixture.deferMatrix = true; });
      await dialog.getByRole("button", { name: "Obnovit výřez", exact: true }).click();
      await page.waitForFunction(() => panel._matrix.loading);
      await page.evaluate(() => {
        fixture.oldMatrix = fixture.resolveMatrix;
        panel._plcs.value = "second"; panel._plcs.dispatchEvent(new Event("change"));
      });
      await page.waitForFunction(() => panel.model.runtime === "runtime-second");
      await page.evaluate(() => fixture.oldMatrix());
      assert.equal(await page.evaluate(() => panel._matrix), null);
      assert.equal(await dialog.evaluate(element => element.open), false);
      await page.evaluate(() => { fixture.deferMatrix = false; });
      await page.getByRole("button", { name: "Otevřít matici", exact: true }).click();
      await page.waitForFunction(() => Boolean(panel._matrix.result));
      await page.evaluate(() => { fixture.connection.connected = false; fixture.event("disconnected"); });
      assert.equal(await page.evaluate(() => panel._matrix), null);
      assert.equal(await dialog.evaluate(element => element.open), false);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("matrix catalog invalidation, read errors, late replies after PLC change and disconnect cleanup");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser, { matrix: true });
      const dialog = page.locator(".matrix-dialog");
      await page.evaluate(() => { fixture.deferMatrix = true; });
      await page.getByRole("button", { name: "Otevřít matici", exact: true }).click();
      await page.waitForFunction(() => Boolean(fixture.resolveMatrix));
      await page.evaluate(() => { fixture.oldMatrix = fixture.resolveMatrix; });
      await page.keyboard.press("Escape");
      await page.waitForFunction(() => panel._matrix === null);
      await page.evaluate(() => {
        fixture.deferMatrix = false;
        fixture.variables[5].name = '<img src="invalid" onerror="window.injected=true">';
        for (const active of fixture.active.values()) active.callback({ ...fixture.snapshot(active.entry), kind: "catalog" });
      });
      await page.getByRole("button", { name: "Otevřít matici", exact: true }).click();
      await page.waitForFunction(() => Boolean(panel._matrix.result));
      assert.equal(await dialog.locator("h2").textContent(), '<img src="invalid" onerror="window.injected=true">');
      const current = await page.evaluate(() => JSON.stringify(panel._matrix.result));
      await page.evaluate(() => {
        fixture.matrixResult = { ...panel._matrix.result, values: panel._matrix.result.values.map(row => row.map(() => 9999)) };
        fixture.oldMatrix();
      });
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => JSON.stringify(panel._matrix.result)), current);
      await page.evaluate(() => { fixture.matrixResult = { values: [] }; });
      await dialog.getByRole("button", { name: "Obnovit výřez", exact: true }).click();
      await page.waitForFunction(() => panel._matrix.error === "matrixError");
      assert.equal(await dialog.locator("tbody tr").count(), 0);
      await page.evaluate(() => fixture.visibility(true));
      assert.equal(await page.evaluate(() => panel._matrix), null);
      const count = await page.evaluate(() => fixture.messages.filter(m => m.type === "amit/monitor/read_matrix").length);
      await page.evaluate(() => fixture.visibility(false));
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => fixture.messages.filter(m => m.type === "amit/monitor/read_matrix").length), count);
      assert.equal(await page.evaluate(() => window.injected), undefined);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("matrix late close/reopen replies, safe text names, malformed response rejection and hidden-page cleanup without automatic reads");
      await page.close();
    }
    for (const suspension of ["hidden", "paused", "disconnected"]) {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak");
      await select(page, "TE_venkovni");
      await page.evaluate(() => fixture.emit(fixture.reading(4102, 18)));
      const history = await page.evaluate(() => JSON.stringify(panel.model.selected.get(4102).points));
      await page.getByRole("spinbutton", { name: "Interval čtení (s)", exact: true }).fill("2.5");
      await page.getByRole("combobox", { name: "Použít interval pro", exact: true }).selectOption("selected");
      await page.getByRole("button", { name: "Použít", exact: true }).click();
      await page.waitForFunction(() => !panel._starting && fixture.subscriptionMessages.at(-1).interval === 2.5);
      await page.evaluate(suspension => {
        if (suspension === "hidden") fixture.visibility(true);
        else if (suspension === "paused") panel.shadowRoot.querySelector(".pause").click();
        else { fixture.connection.connected = false; fixture.event("disconnected"); }
      }, suspension);
      await page.waitForFunction(() => fixture.active.size === 0);
      const calls = await page.evaluate(() => fixture.calls);
      await page.evaluate(suspension => {
        if (suspension === "paused") fixture.variables.find(v => v.wid === 4101).readable = false;
        else fixture.variables = fixture.variables.filter(v => v.wid !== 4101);
        fixture.deferSnapshot = suspension === "hidden";
        if (suspension === "hidden") fixture.visibility(false);
        else if (suspension === "paused") panel.shadowRoot.querySelector(".pause").click();
        else { fixture.connection.connected = true; fixture.event("ready"); }
      }, suspension);
      await page.waitForFunction(() => fixture.active.size === 1 && !panel._starting &&
        !panel._subscriptionFailed && fixture.subscriptionMessages.at(-1).wids?.length === 1);
      assert.deepEqual(await page.evaluate(calls => fixture.subscriptionMessages.slice(calls), calls), [
        { type: "amit/monitor/subscribe", entry_id: "first", interval: 2.5, wids: [4101, 4102] },
        { type: "amit/monitor/subscribe", entry_id: "first" },
        { type: "amit/monitor/subscribe", entry_id: "first", interval: 2.5, wids: [4102] },
      ]);
      assert.equal(await page.evaluate(() => JSON.stringify(panel.model.selected.get(4102).points)), history);
      assert.equal(await page.evaluate(() => panel.model.selected.has(4101)), false);
      await page.evaluate(() => fixture.emit(fixture.reading(4102, 19)));
      assert.equal(await page.evaluate(() => panel.model.selected.get(4102).points.length), 2);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push(`selection recovers after catalog change while ${suspension}; remaining history and requested interval survive`);
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak");
      await page.getByRole("spinbutton", { name: "Interval čtení (s)", exact: true }).fill("2");
      await page.getByRole("combobox", { name: "Použít interval pro", exact: true }).selectOption("selected");
      await page.getByRole("button", { name: "Použít", exact: true }).click();
      await page.waitForFunction(() => !panel._starting && fixture.subscriptionMessages.at(-1).interval === 2);
      await page.evaluate(() => fixture.visibility(true));
      await page.waitForFunction(() => fixture.active.size === 0);
      const calls = await page.evaluate(() => fixture.calls);
      await page.evaluate(() => { fixture.rejectSelected = true; fixture.visibility(false); });
      await page.waitForFunction(() => panel._subscriptionFailed && fixture.active.size === 0);
      await page.waitForTimeout(200);
      assert.equal(await page.evaluate(() => fixture.calls), calls + 3, "Recovery must stop after one catalog refresh and one retry");
      await page.getByRole("alert").filter({ hasText: "Interval se nepodařilo" }).waitFor();
      await page.getByRole("button", { name: "Použít interval zařízení", exact: true }).click();
      await page.waitForFunction(() => fixture.active.size === 1 && !panel._starting && !panel._subscriptionFailed);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("selection recovery is bounded; a repeated rejection releases the temporary subscription and device reset recovers");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      const input = page.getByRole("spinbutton", { name: "Interval čtení (s)", exact: true });
      const apply = page.getByRole("button", { name: "Použít", exact: true });
      const reset = page.getByRole("button", { name: "Použít interval zařízení", exact: true });
      const scope = page.getByRole("combobox", { name: "Použít interval pro", exact: true });
      await select(page, "TE_obyvak");
      await page.evaluate(() => fixture.emit(fixture.reading(4101, 23)));
      const count = await page.evaluate(() => panel.model.count);
      const calls = await page.evaluate(() => fixture.calls);
      for (const value of ["", "0", "120.1"]) {
        await input.fill(value);
        await apply.click();
        await page.getByRole("alert").filter({ hasText: "Zadejte číslo" }).waitFor();
        assert.equal(await page.evaluate(() => fixture.calls), calls);
      }
      await input.fill("2.5");
      await scope.selectOption("selected");
      await apply.click();
      await page.waitForFunction(() => !panel._starting && panel._unsubscribe && fixture.subscriptionMessages.at(-1).interval === 2.5);
      assert.deepEqual(await page.evaluate(() => fixture.subscriptionMessages.at(-1)),
        { type: "amit/monitor/subscribe", entry_id: "first", interval: 2.5, wids: [4101] });
      assert.equal(await page.evaluate(() => panel.model.count), count);
      await select(page, "TE_venkovni");
      await page.waitForFunction(() => fixture.subscriptionMessages.at(-1).wids?.length === 2 && !panel._starting);
      await page.getByRole("searchbox").fill("Provozni");
      await page.waitForTimeout(150);
      assert.deepEqual(await page.evaluate(() => fixture.subscriptionMessages.at(-1).wids), [4101, 4102]);
      await page.getByRole("searchbox").fill("");
      await page.getByRole("checkbox", { name: "Vybráno: TE_obyvak", exact: true }).uncheck();
      await page.getByRole("checkbox", { name: "Vybráno: TE_venkovni", exact: true }).uncheck();
      await page.waitForFunction(() => fixture.subscriptionMessages.at(-1).wids?.length === 0 && !panel._starting);
      await input.fill("120");
      await scope.selectOption("all");
      await apply.click();
      await page.waitForFunction(() => fixture.subscriptionMessages.at(-1).interval === 120 && !panel._starting);
      assert.equal(await page.evaluate(() => "wids" in fixture.subscriptionMessages.at(-1)), false);
      await input.fill("17");
      await page.waitForTimeout(1100);
      assert.equal(await input.inputValue(), "17", "Rendering must preserve an unapplied draft");
      await page.getByRole("button", { name: "Pozastavit", exact: true }).click();
      await page.waitForFunction(() => fixture.active.size === 0);
      await page.getByRole("button", { name: "Pokračovat", exact: true }).click();
      await page.waitForFunction(() => fixture.active.size === 1 && !panel._starting);
      assert.equal(await page.evaluate(() => fixture.subscriptionMessages.at(-1).interval), 120);
      await page.evaluate(() => fixture.visibility(true));
      await page.waitForFunction(() => fixture.active.size === 0);
      await page.evaluate(() => fixture.visibility(false));
      await page.waitForFunction(() => fixture.active.size === 1 && !panel._starting);
      await page.evaluate(() => { fixture.connection.connected = false; fixture.event("disconnected"); });
      await page.waitForFunction(() => fixture.active.size === 0);
      await page.evaluate(() => { fixture.connection.connected = true; fixture.event("ready"); });
      await page.waitForFunction(() => fixture.active.size === 1 && !panel._starting);
      assert.equal(await page.evaluate(() => fixture.subscriptionMessages.at(-1).interval), 120);
      await reset.click();
      await page.waitForFunction(() => !panel._starting && !("interval" in fixture.subscriptionMessages.at(-1)));
      assert.equal(await input.inputValue(), "30");
      await input.fill("1"); await apply.click();
      await page.waitForFunction(() => fixture.subscriptionMessages.at(-1).interval === 1 && !panel._starting);
      await page.getByRole("combobox", { name: "PLC", exact: true }).selectOption("second");
      await page.waitForFunction(() => fixture.subscriptionMessages.at(-1).entry_id === "second" && !panel._starting);
      assert.equal(await page.evaluate(() => "interval" in fixture.subscriptionMessages.at(-1)), false);
      await input.fill("5"); await apply.click();
      await page.waitForFunction(() => fixture.subscriptionMessages.at(-1).interval === 5 && !panel._starting);
      await page.setViewportSize({ width: 390, height: 844 });
      await theme(page, true);
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => panel.shadowRoot.querySelector(".interval-settings").scrollWidth <= panel.clientWidth), true);
      if (process.env.AMIT_SCREENSHOT_DIR) {
        await fs.mkdir(process.env.AMIT_SCREENSHOT_DIR, { recursive: true });
        await page.screenshot({ path: path.join(process.env.AMIT_SCREENSHOT_DIR, "interval-mobile-dark.png"), fullPage: true });
      }
      await page.evaluate(() => panel.remove());
      await page.waitForFunction(() => fixture.active.size === 0);
      await page.evaluate(() => document.body.append(panel));
      await page.waitForFunction(() => fixture.active.size === 1 && !panel._starting);
      assert.equal(await page.evaluate(() => "interval" in fixture.subscriptionMessages.at(-1)), false);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("custom numeric intervals, selected and all scope, dynamic selection, history retention, draft retention, pause, hide, reconnect, reset, PLC change and panel close");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await page.evaluate(() => { fixture.subscriptionError = { code: "invalid_request" }; });
      await page.getByRole("spinbutton", { name: "Interval čtení (s)", exact: true }).fill("2");
      await page.getByRole("button", { name: "Použít", exact: true }).click();
      await page.getByRole("alert").filter({ hasText: "Interval se nepodařilo" }).waitFor();
      assert.equal(await page.evaluate(() => fixture.active.size), 0);
      await page.evaluate(() => { fixture.subscriptionError = null; });
      await page.evaluate(() => {
        fixture.connection.connected = false; fixture.event("disconnected");
        fixture.connection.connected = true; fixture.event("ready");
      });
      await page.waitForFunction(() => fixture.active.size === 1 && !panel._starting && panel._intervalError === null);
      assert.equal(await page.evaluate(() => fixture.subscriptionMessages.at(-1).interval), 2);
      await page.evaluate(() => { fixture.subscriptionError = { code: "invalid_request" }; });
      await page.getByRole("spinbutton", { name: "Interval čtení (s)", exact: true }).fill("3");
      await page.getByRole("spinbutton", { name: "Interval čtení (s)", exact: true }).press("Enter");
      await page.getByRole("alert").filter({ hasText: "Interval se nepodařilo" }).waitFor();
      await page.evaluate(() => { fixture.subscriptionError = null; });
      await page.getByRole("button", { name: "Použít interval zařízení", exact: true }).click();
      await page.waitForFunction(() => fixture.active.size === 1 && !panel._starting);
      assert.equal(await page.evaluate(() => panel._intervalError), null);
      await page.evaluate(() => {
        for (const active of fixture.active.values()) active.callback({ ...fixture.snapshot(active.entry), scan_interval: 60 });
      });
      assert.equal(await page.getByRole("spinbutton", { name: "Interval čtení (s)", exact: true }).inputValue(), "60");
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("rejected interval reports failure; reconnect and device reset recover; Enter submits; device interval populates input");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak");
      await page.getByRole("spinbutton", { name: "Interval čtení (s)", exact: true }).fill("120");
      await page.getByRole("combobox", { name: "Použít interval pro", exact: true }).selectOption("selected");
      await page.getByRole("button", { name: "Použít", exact: true }).click();
      await page.waitForFunction(() => !panel._starting && fixture.subscriptionMessages.at(-1).interval === 120);
      await page.evaluate(() => fixture.emit({ ...fixture.reading(4101, 24), timestamp: new Date(Date.now() - 90000).toISOString() }));
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => panel._rows.get(4101).reading.textContent.includes("Zastaralé")), false);
      const before = await page.evaluate(() => JSON.stringify([...panel.model.selected]));
      await page.evaluate(() => {
        for (const active of fixture.active.values()) active.callback({ kind: "intervals", runtime_id: "runtime-first", intervals: { 4101: 10 } });
      });
      await page.waitForFunction(() => panel._rows.get(4101).reading.textContent.includes("Zastaralé"));
      assert.equal(await page.evaluate(() => JSON.stringify([...panel.model.selected])), before);
      await page.evaluate(() => {
        fixture.variables = fixture.variables.filter(v => v.wid !== 4101);
        for (const active of fixture.active.values()) active.callback({ ...fixture.snapshot(active.entry), kind: "catalog" });
      });
      await page.waitForFunction(() => fixture.subscriptionMessages.at(-1).wids?.length === 0 && !panel._starting);
      assert.equal(await page.evaluate(() => panel.model.selected.size), 0);
      await page.evaluate(() => { fixture.deferSubscription = true; });
      await select(page, "TE_venkovni");
      await page.waitForFunction(() => fixture.pending.length === 1);
      await page.getByRole("button", { name: "Použít interval zařízení", exact: true }).click();
      await page.waitForFunction(() => fixture.pending.length === 2);
      await page.evaluate(() => { for (const resolve of fixture.pending.splice(0)) resolve(); });
      await page.waitForFunction(() => fixture.active.size === 1 && !panel._starting);
      assert.equal(await page.evaluate(() => "interval" in fixture.subscriptionMessages.at(-1)), false);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("per-WID staleness, catalog selection removal, and late custom-subscription cleanup after interval reset");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      const original = await page.locator("amit-monitor-panel tbody .name").allTextContents();
      await page.getByRole("searchbox").fill("TE_venkovni");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 1);
      await page.evaluate(() => { window.retainedRow = panel.shadowRoot.querySelector("tbody tr"); });
      await page.getByRole("searchbox").fill("");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 7);
      const restored = await page.locator("amit-monitor-panel tbody .name").allTextContents();
      await select(page, "TE_obyvak");
      await page.evaluate(() => {
        fixture.emit(fixture.reading(4101, .049)); fixture.emit(fixture.reading(4101, .0495));
      });
      await page.waitForFunction(() => panel.shadowRoot.querySelector(".chart path"));
      const labels = await page.locator('amit-monitor-panel .chart svg text[text-anchor="end"][x="58"]').allTextContents();
      assert.deepEqual({ order: restored, distinctLabels: new Set(labels).size },
        { order: original, distinctLabels: 3 }, "Search reset must restore catalog order and small Float ticks must differ");
      assert.equal(await page.evaluate(() => panel._rows.get(4102).row === retainedRow), true);
      const checkbox = page.getByRole("checkbox", { name: "Vybráno: TE_venkovni", exact: true });
      await checkbox.focus();
      await page.waitForTimeout(1100);
      assert.equal(await checkbox.evaluate(e => e.getRootNode().activeElement === e), true);
      await page.getByRole("combobox", { name: "Typ proměnné", exact: true }).selectOption("Long");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 1);
      await page.getByRole("combobox", { name: "Typ proměnné", exact: true }).selectOption("all");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 7);
      assert.deepEqual(await page.locator("amit-monitor-panel tbody .name").allTextContents(), original);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("distinct small Float axis labels; catalog order and retained row focus after resetting search/type filters");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      assert.equal(await page.locator("amit-monitor-panel tbody tr").count(), 7);
      assert.equal(await page.locator("amit-monitor-panel img").count(), 0);
      assert.equal(await page.evaluate(() => window.injected), undefined);
      await page.getByRole("searchbox").fill("4101");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 1);
      await page.getByRole("searchbox").fill("");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 7);
      await select(page, "TE_obyvak"); await select(page, "Zap_cerpadlo");
      assert.equal(await page.evaluate(() => panel.model.count), 0);
      await page.evaluate(() => {
        fixture.emit(fixture.reading(4101, 22.5)); fixture.emit(fixture.reading(4301, 0));
        fixture.emit(fixture.reading(4101, 22.8)); fixture.emit(fixture.reading(4301, 1));
        fixture.emit(fixture.reading(4101, null, "read_error")); fixture.emit(fixture.reading(4101, 22.9));
      });
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll(".chart path").length === 2);
      const paths = await page.locator("amit-monitor-panel .chart path").evaluateAll(paths => paths.map(p => p.getAttribute("d")));
      assert.equal((paths[0].match(/M/g) || []).length, 2);
      assert.ok(paths[1].includes("H") && paths[1].includes("V"));
      assert.equal(await page.locator("amit-monitor-panel .chart").first().locator("circle").count(), 1);
      const beforeMetadata = await page.evaluate(() => JSON.stringify([...panel.model.selected]));
      await page.evaluate(() => {
        for (const active of fixture.active.values()) active.callback({
          kind: "entity_metadata", runtime_id: `runtime-${active.entry}`,
          variables: [{ wid: 4101, configured: true, entities: [
            { entity_id: "sensor.renamed", name: "TE_obyvak", custom_name: null, disabled: false },
          ] }],
        });
      });
      assert.equal(await page.evaluate(() => JSON.stringify([...panel.model.selected])), beforeMetadata,
        "Entity metadata must preserve recorded samples and pending graph gaps");
      const range = page.getByRole("slider", { name: "Vzorek: TE_obyvak", exact: true });
      await range.focus(); await range.press("Home");
      assert.equal(await range.getAttribute("aria-valuetext").then(v => v.includes("22,5")), true);
      const beforePause = await page.evaluate(() => panel.model.count);
      await page.getByRole("button", { name: "Pozastavit", exact: true }).click();
      await page.waitForFunction(() => fixture.active.size === 0);
      await page.evaluate(() => fixture.oldCallback({ kind: "sample", runtime_id: "runtime-first", sample: fixture.reading(4101, 999) }));
      assert.equal(await page.evaluate(() => panel.model.count), beforePause);
      await page.getByRole("button", { name: "Pokračovat", exact: true }).click();
      await page.waitForFunction(() => fixture.active.size === 1);
      assert.equal(await page.evaluate(() => panel.model.count), beforePause);
      await page.evaluate(() => fixture.emit(fixture.reading(4101, 23)));
      assert.equal(await page.evaluate(() => panel.model.selected.get(4101).points.at(-1).breakBefore), true);
      await page.evaluate(() => fixture.visibility(true));
      await page.waitForFunction(() => fixture.active.size === 0);
      await page.evaluate(() => fixture.visibility(false));
      await page.waitForFunction(() => fixture.active.size === 1);
      await page.evaluate(() => { fixture.connection.connected = false; fixture.active.clear(); fixture.event("disconnected"); });
      await page.evaluate(() => { fixture.connection.connected = true; fixture.event("ready"); });
      await page.waitForFunction(() => fixture.active.size === 1);
      await page.getByRole("button", { name: "Vymazat historii", exact: true }).click();
      assert.equal(await page.evaluate(() => panel.model.count), 0);
      assert.equal(await page.evaluate(() => panel.model.selected.size), 2);
      await page.evaluate(() => { fixture.emit(fixture.reading(4101, 24)); panel.remove(); });
      await page.waitForFunction(() => fixture.active.size === 0);
      assert.deepEqual(await page.evaluate(() => [panel.model.count, panel.model.selected.size, panel.model.latest.size, panel.shadowRoot.querySelectorAll(".chart").length]), [0, 0, 0, 0]);
      await page.evaluate(() => document.body.append(panel));
      await page.waitForFunction(() => fixture.active.size === 1);
      assert.equal(await page.evaluate(() => panel.model.selected.size), 0);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("search, XSS-safe names, fresh samples, integer steps, error gaps, keyboard details, pause, visibility, reconnect, clear, close/reopen");
      await page.close();
    }
    {
      const { page, errors } = await mount(browser, { deferSubscription: true });
      await page.getByRole("button", { name: "Pozastavit", exact: true }).click();
      await page.evaluate(() => fixture.pending.splice(0).forEach(resolve => resolve()));
      await page.waitForFunction(() => fixture.active.size === 0);
      await page.evaluate(() => { fixture.deferSubscription = false; });
      await page.getByRole("button", { name: "Pokračovat", exact: true }).click();
      await page.waitForFunction(() => fixture.active.size === 1);
      await page.getByRole("combobox", { name: "PLC", exact: true }).selectOption("second");
      await page.waitForFunction(() => fixture.active.size === 1 && [...fixture.active.values()][0].entry === "second");
      await select(page, "TE_obyvak");
      await page.evaluate(() => fixture.emit(fixture.reading(4101, 8)));
      await page.evaluate(() => {
        fixture.entries = fixture.entries.filter(e => e.entry_id !== "second");
        for (const active of fixture.active.values()) active.callback({ kind: "unavailable", runtime_id: "runtime-second" });
      });
      await page.waitForFunction(() => panel._unavailable && fixture.active.size === 0);
      assert.equal(await page.evaluate(() => panel._entryId), "second");
      assert.deepEqual(errors, []);
      results.push("pending subscription cleanup, PLC selection, unavailable PLC without fallback");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak"); await select(page, "TE_venkovni");
      await page.evaluate(() => {
        fixture.variables.find(v => v.wid === 0).name = "Stav_vetrani";
        for (const active of fixture.active.values()) active.callback({ ...fixture.snapshot(active.entry), kind: "catalog" });
        for (let i = 0; i < 31; i++) {
          fixture.emit(fixture.reading(4101, Math.round((21.8 + i * .02 + Math.sin(i / 3) * .1) * 100) / 100));
          fixture.emit(fixture.reading(4102, Math.round((9.3 - i * .02 + Math.sin(i / 3) * .08) * 100) / 100));
        }
      });
      for (const dark of [false, true]) {
        await theme(page, dark);
        for (const width of [1024, 736, 390, 320]) {
          await page.setViewportSize({ width, height: 1000 });
          await page.waitForTimeout(180);
          const metrics = await page.evaluate(() => {
            const root = panel.shadowRoot;
            const overflow = [...root.querySelectorAll(".section,.meta,header,.columns")].filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.className || e.tagName);
            const clipped = [...root.querySelectorAll(".chart svg text")].filter(e => {
              const text = e.getBoundingClientRect(), svg = e.ownerSVGElement.getBoundingClientRect();
              return text.left < svg.left - 1 || text.right > svg.right + 1;
            }).map(e => e.textContent);
            return { overflow, clipped, pageWidth: document.documentElement.scrollWidth, selected: panel.model.selected.size };
          });
          assert.equal(metrics.pageWidth, width); assert.deepEqual(metrics.overflow, [], JSON.stringify({ width, dark, metrics }));
          assert.deepEqual(metrics.clipped, [], JSON.stringify({ width, dark, metrics }));
          if (process.env.AMIT_SCREENSHOT_DIR && [1024, 390].includes(width)) {
            await fs.mkdir(process.env.AMIT_SCREENSHOT_DIR, { recursive: true });
            await page.screenshot({ path: path.join(process.env.AMIT_SCREENSHOT_DIR, `amit-panel-${dark ? "dark" : "light"}-${width}.png`), fullPage: true });
          }
        }
      }
      await page.evaluate(() => { panel.hass = { ...panel._hass, language: "en" }; });
      await page.getByRole("searchbox", { name: "Search name or WID…", exact: true }).waitFor();
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("light/dark layout at 320, 390, 736 and 1024 px; English/Czech; no clipped chart labels or external requests");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await page.evaluate(() => {
        fixture.variables = Array.from({ length: 151 }, (_, wid) => ({
          wid, revision: wid + 1, name: `Variable ${wid}`, type: wid === 1 ? "Long" : "Float", unit: null, readable: true,
        }));
        for (const active of fixture.active.values()) active.callback({ ...fixture.snapshot(active.entry), kind: "catalog", samples: [] });
      });
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 50);
      for (let i = 0; i < 6; i++) await select(page, `Variable ${i}`);
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll(".chart").length === 4);
      await page.evaluate(() => {
        [3.4e38, 2147483647, 1e-38, -3.4e38, 0, -2147483648].forEach((v, wid) => fixture.emit(fixture.reading(wid, v)));
      });
      assert.equal(await page.evaluate(() => panel._format(2147483647).replace(/\D/g, "")), "2147483647");
      await page.setViewportSize({ width: 320, height: 1000 });
      await page.waitForTimeout(180);
      const clipped = await page.locator("amit-monitor-panel .chart svg text").evaluateAll(elements => elements.filter(e => {
        const r = e.getBoundingClientRect(), s = e.ownerSVGElement.getBoundingClientRect();
        return r.left < s.left - 1 || r.right > s.right + 1;
      }).map(e => e.textContent));
      assert.deepEqual(clipped, []);
      const nextTable = page.locator("amit-monitor-panel .table-pager").getByRole("button", { name: "Další strana", exact: true });
      await nextTable.click();
      await page.waitForFunction(() => panel._tablePage === 1 && panel.shadowRoot.querySelector("tbody .name").textContent === "Variable 50");
      await nextTable.focus();
      await page.waitForTimeout(1100);
      assert.equal(await nextTable.evaluate(e => e.getRootNode().activeElement === e), true);
      await page.locator("amit-monitor-panel .chart-pager").getByRole("button", { name: "Další strana", exact: true }).click();
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll(".chart").length === 2);
      assert.equal(await page.evaluate(() => panel.model.count), 6);
      await page.getByRole("searchbox").fill("Variable 150");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 1);
      await page.getByRole("checkbox", { name: "Vybráno: Variable 150", exact: true }).check();
      await page.evaluate(() => { window.dispatchEvent(new Event("pagehide")); });
      await page.waitForFunction(() => fixture.active.size === 0);
      assert.deepEqual(await page.evaluate(() => [panel.model.count, panel.model.selected.size]), [0, 0]);
      await page.evaluate(() => window.dispatchEvent(new Event("pageshow")));
      await page.waitForFunction(() => fixture.active.size === 1);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("151-variable pagination, graph pagination, keyboard focus, Int32 precision, extreme Float axes, pagehide/pageshow cleanup");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await page.evaluate(() => fixture.metadata([
        { wid: 4101, configured: true, entities: [
          { entity_id: "sensor.living_room", name: "Teplota obýváku", custom_name: "Teplota obýváku", disabled: false },
        ] },
        { wid: 4102, configured: true, entities: [
          { entity_id: "sensor.outdoor", name: "Venkovní teplota", custom_name: "Venkovní teplota", disabled: false },
          { entity_id: "binary_sensor.outdoor_alarm", name: "Venkovní alarm", custom_name: "Venkovní alarm", disabled: true },
        ] },
        { wid: 4201, configured: true, entities: [] },
      ]));
      await page.waitForFunction(() => panel._rows.get(4101).name.textContent === "Teplota obýváku");
      assert.ok((await page.locator("amit-monitor-panel tbody").textContent()).includes("Vybraná v konfiguraci HA · bez entity"));
      assert.ok((await page.evaluate(() => panel._rows.get(4102).entities.textContent)).includes("Zakázaná"));
      await select(page, "Teplota obýváku"); await select(page, "Zap_cerpadlo");
      await page.evaluate(() => {
        fixture.emit(fixture.reading(4101, 22)); fixture.emit(fixture.reading(4301, 0));
        fixture.emit(fixture.reading(4101, 23)); fixture.emit(fixture.reading(4301, 1));
      });
      const haFilter = page.getByRole("combobox", { name: "Entity Home Assistantu", exact: true });
      await haFilter.selectOption("ha");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 2);
      assert.equal(await page.evaluate(() => panel.model.selected.size), 2);
      await page.evaluate(() => fixture.emit(fixture.reading(4301, 0)));
      assert.equal(await page.evaluate(() => panel.model.selected.get(4301).points.length), 3);
      assert.equal(await page.evaluate(() => fixture.calls), 1, "Filtering must not resubscribe");
      for (const query of ["obýváku", "TE_obyvak", "4101", "Venkovní alarm"]) {
        await page.getByRole("searchbox").fill(query);
        await page.waitForFunction(expected => panel.shadowRoot.querySelectorAll("tbody tr").length === 1 &&
          panel.shadowRoot.querySelector("tbody").textContent.includes(expected), query === "Venkovní alarm" ? "TE_venkovni" : "TE_obyvak");
      }
      await page.getByRole("searchbox").fill("");
      await page.getByRole("combobox", { name: "Typ proměnné", exact: true }).selectOption("Int");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 0);
      await page.getByRole("combobox", { name: "Typ proměnné", exact: true }).selectOption("all");
      await page.waitForFunction(() => panel.shadowRoot.querySelectorAll("tbody tr").length === 2);
      await page.getByRole("checkbox", { name: "Vybráno: Teplota obýváku", exact: true }).focus();
      const before = await page.evaluate(() => {
        window.metadataRow = panel._rows.get(4101).row;
        return JSON.stringify([...panel.model.selected]);
      });
      await page.evaluate(() => fixture.metadata([{ wid: 4101, configured: true, entities: [
        { entity_id: "sensor.renamed", name: "Teplota pokoje", custom_name: "Teplota pokoje", disabled: true },
      ] }]));
      await page.waitForFunction(() => panel._charts.get(4101).name.textContent === "Teplota pokoje");
      assert.equal(await page.evaluate(() => JSON.stringify([...panel.model.selected])), before);
      assert.equal(await page.evaluate(() => panel._rows.get(4101).row === metadataRow), true);
      assert.equal(await page.getByRole("checkbox", { name: "Vybráno: Teplota pokoje", exact: true })
        .evaluate(e => e.getRootNode().activeElement === e), true);
      assert.ok((await page.evaluate(() => panel._charts.get(4101).identity.textContent)).includes("TE_obyvak"));
      assert.ok((await page.evaluate(() => panel._charts.get(4101).entities.textContent)).includes("Zakázaná"));
      await page.getByRole("slider", { name: "Vzorek: Teplota pokoje", exact: true }).focus();
      await page.getByRole("slider", { name: "Vzorek: Teplota pokoje", exact: true }).press("Home");
      assert.equal(await page.getByRole("slider", { name: "Vzorek: Teplota pokoje", exact: true })
        .getAttribute("aria-valuetext").then(v => v.includes("22")), true);
      await page.evaluate(() => fixture.metadata([{ wid: 4101, configured: true, entities: [] }]));
      await page.waitForFunction(() => panel._charts.get(4101).name.textContent === "TE_obyvak" && !panel._rows.has(4101));
      assert.equal(await page.evaluate(() => JSON.stringify([...panel.model.selected])), before);
      await page.evaluate(() => fixture.metadata([{ wid: 4101, configured: true, entities: [
        { entity_id: "sensor.living_room", name: "Teplota obýváku po přejmenování s delším vlastním názvem", custom_name: "Teplota obýváku po přejmenování s delším vlastním názvem", disabled: false },
      ] }]));
      await page.waitForFunction(() => panel._rows.has(4101));
      for (const dark of [false, true]) {
        await theme(page, dark);
        for (const width of [320, 390, 1024]) {
          await page.setViewportSize({ width, height: 1000 });
          await page.waitForTimeout(180);
          assert.deepEqual(await page.evaluate(() => [...panel.shadowRoot.querySelectorAll(".section,.tools,.meta")]
            .filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.className)), []);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
          if (process.env.AMIT_SCREENSHOT_DIR && width !== 320) await page.screenshot({
            path: path.join(process.env.AMIT_SCREENSHOT_DIR, `amit-entity-names-${dark ? "dark" : "light"}-${width}.png`), fullPage: true,
          });
        }
      }
      await page.evaluate(() => { panel.hass = { ...panel._hass, language: "en" }; });
      await page.getByRole("combobox", { name: "Home Assistant entities", exact: true }).waitFor();
      await page.waitForFunction(() => panel._rows.get(4102).entities.textContent.includes("Disabled"));
      await page.getByRole("combobox", { name: "Home Assistant entities", exact: true }).selectOption("all");
      await page.evaluate(() => fixture.metadata([{ wid: 0, configured: true, entities: [
        { entity_id: 'sensor.<img src="bad" onerror="window.injected=true">', name: '<img src="bad" onerror="window.injected=true">', custom_name: null, disabled: false },
      ] }]));
      await page.waitForFunction(() => panel._rows.has(0));
      assert.equal(await page.locator("amit-monitor-panel img").count(), 0);
      assert.equal(await page.evaluate(() => window.injected), undefined);
      await page.getByRole("button", { name: "Pause", exact: true }).click();
      await page.getByRole("button", { name: "Resume", exact: true }).click();
      await page.waitForFunction(() => panel.model.catalog.get(4101).entities.length === 1 && fixture.active.size === 1);
      await page.getByRole("combobox", { name: "PLC", exact: true }).selectOption("second");
      await page.waitForFunction(() => panel.model.runtime === "runtime-second" && panel._rows.get(4101)?.name.textContent === "TE_obyvak");
      assert.equal(await page.evaluate(() => panel.model.catalog.get(4101).entities.length), 0);
      assert.equal(await page.evaluate(() => panel.model.selected.size), 0);
      assert.equal(await page.evaluate(() => panel._rows.get(4101).name.textContent), "TE_obyvak");
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("HA names, original PLC identity, disabled and multiple entities, combined filters, rename/removal without history loss, safe text, mobile themes, reconnect and PLC isolation");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak");
      await page.evaluate(() => {
        fixture.emit(fixture.reading(4101, 25));
        fixture.variables.push(...Array.from({ length: 55 }, (_, i) => ({
          wid: 5000 + i, name: `Extra ${i}`, type: "Float", revision: 20 + i, readable: true,
        })));
        for (const active of fixture.active.values()) active.callback(fixture.snapshot(active.entry));
      });
      await page.locator("amit-monitor-panel .table-pager").getByRole("button", { name: "Další strana", exact: true }).click();
      await select(page, "Extra 54");
      await page.getByRole("searchbox").fill("nothing matches");
      await page.getByRole("button", { name: "Přidat vybrané jako HA entity", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("button", { name: "Uložit a načíst entity", exact: true }).waitFor();
      assert.deepEqual(await page.evaluate(() => fixture.messages.find(m => m.type === "amit/monitor/preview_add").variables.map(v => v.wid)), [4101, 5054]);
      assert.equal(await dialog.getByRole("listitem").count(), 2);
      assert.ok((await dialog.textContent()).includes("Extra 54"));
      assert.ok((await dialog.textContent()).includes("Opětovné načtení vymaže dočasnou historii"));
      await dialog.getByRole("button", { name: "Zrušit", exact: true }).click();
      await page.waitForFunction(() => panel._addition === null);
      assert.equal(await page.evaluate(() => panel.model.count), 1);
      assert.equal(await page.evaluate(() => fixture.messages.some(m => m.type === "amit/monitor/confirm_add")), false);
      assert.equal(await page.evaluate(() => panel.shadowRoot.activeElement.className), "add-entities");
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("permanent addition includes selected variables across pages and filters; cancel preserves history and focus without saving");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak");
      await page.evaluate(() => {
        fixture.emit(fixture.reading(4101, 26));
        const variables = fixture.snapshot("first").variables.filter(v => [4101, 4102, 0].includes(v.wid));
        variables[0].entities = [{ entity_id: "sensor.living_room", name: "Obývák – vlastní název", custom_name: "Obývák – vlastní název", disabled: true }];
        fixture.preview = { preview_id: "all-preview", expires_at: Math.floor(Date.now() / 1000) + 300,
          requested_wids: [4101], added_wids: [], already_configured_wids: [4101], newly_monitored_wids: [4102, 0],
          removed_write_wids: [999], selection_mode: "all", requires_reload: true, variables };
      });
      await page.getByRole("button", { name: "Přidat vybrané jako HA entity", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("button", { name: "Uložit a načíst entity", exact: true }).waitFor();
      assert.equal(await dialog.getByRole("listitem").count(), 3);
      for (const text of ["všechny čitelné proměnné", "Obývák – vlastní název", "Zakázaná", "WID 999", "<img src="])
        assert.ok((await dialog.textContent()).includes(text), text);
      assert.equal(await dialog.locator("img").count(), 0);
      for (const dark of [false, true]) {
        await theme(page, dark);
        for (const width of [320, 390, 1024]) {
          await page.setViewportSize({ width, height: 1000 });
          await page.waitForTimeout(180);
          assert.equal(await dialog.evaluate(e => e.scrollWidth <= e.clientWidth + 1), true);
          const contrast = await dialog.evaluate(e => {
            const context = document.createElement("canvas").getContext("2d");
            const luminance = color => {
              context.fillStyle = color; context.fillRect(0, 0, 1, 1);
              const channels = [...context.getImageData(0, 0, 1, 1).data].slice(0, 3).map(v => {
                const c = v / 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
              });
              return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
            };
            return [...e.querySelectorAll(".addition-warning,.primary")].map(element => {
              const style = getComputedStyle(element), a = luminance(style.color), b = luminance(style.backgroundColor);
              return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
            });
          });
          assert.ok(contrast.every(ratio => ratio >= 4.5), `Dialog text contrast: ${contrast}`);
          await page.keyboard.press("Tab");
          assert.equal(await dialog.evaluate(e => {
            const active = e.getRootNode().activeElement;
            return e.contains(active) || (active === null && document.activeElement === document.body);
          }), true);
          if (process.env.AMIT_SCREENSHOT_DIR) await page.screenshot({
            path: path.join(process.env.AMIT_SCREENSHOT_DIR, `amit-addition-${dark ? "dark" : "light"}-${width}.png`), fullPage: true,
          });
        }
      }
      await page.evaluate(() => { panel.hass = { ...panel._hass, language: "en" }; });
      await dialog.getByRole("button", { name: "Save and load entities", exact: true }).click();
      await page.waitForFunction(() => panel._addition?.phase === "pending");
      assert.equal(await page.evaluate(() => panel.model.count), 1);
      await dialog.getByRole("button", { name: "Close", exact: true }).click();
      await page.evaluate(() => {
        fixture.entries = [];
        for (const active of [...fixture.active.values()]) active.callback({ kind: "unavailable", runtime_id: "runtime-first" });
      });
      await page.waitForFunction(() => panel._unavailable && panel._entries.length === 0);
      assert.ok((await page.locator("amit-monitor-panel .addition-status").textContent()).includes("Selection saved"));
      await page.evaluate(() => { fixture.connection.connected = false; fixture.event("disconnected"); });
      await page.evaluate(() => {
        fixture.entries = [{ entry_id: "first", title: "Vytápění · Biosuntec" }];
        fixture.additionStatus = "loaded";
        fixture.connection.connected = true; fixture.event("ready");
      });
      await page.waitForFunction(() => panel._addition?.phase === "loaded" && panel.model.runtime === "runtime-first-reloaded");
      assert.equal(await page.evaluate(() => panel.model.count), 0);
      assert.equal(await page.evaluate(() => fixture.messages.filter(m => m.type === "amit/monitor/confirm_add").length), 1);
      assert.equal(await page.evaluate(() => panel._entryId), "first");
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("all-mode full preview, safe names and disabled entities, mobile modal themes and keyboard focus, saved/pending/loaded states, final-PLC reload and reconnect with history reset");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak");
      await page.evaluate(() => { fixture.deferPreview = true; });
      await page.getByRole("button", { name: "Přidat vybrané jako HA entity", exact: true }).click();
      await page.waitForFunction(() => Boolean(fixture.resolvePreview));
      await page.getByRole("dialog").getByRole("button", { name: "Zrušit", exact: true }).click();
      await page.evaluate(() => { fixture.resolvePreview(); fixture.deferPreview = false; });
      await page.waitForFunction(() => panel._addition === null);
      await page.getByRole("button", { name: "Přidat vybrané jako HA entity", exact: true }).click();
      await page.waitForFunction(() => panel._addition?.phase === "preview");
      await page.evaluate(() => fixture.metadata([{ wid: 4101, configured: false, entities: [
        { entity_id: "sensor.changed", name: "Renamed", custom_name: "Renamed", disabled: false },
      ] }]));
      await page.waitForFunction(() => panel._addition?.phase === "stale");
      await page.getByRole("dialog").getByRole("button", { name: "Uložit a načíst entity", exact: true }).waitFor({ state: "hidden" });
      await page.getByRole("dialog").getByRole("button", { name: "Připravit nový náhled", exact: true }).click();
      await page.waitForFunction(() => panel._addition?.phase === "preview");
      await page.evaluate(() => {
        fixture.connection.connected = false; fixture.event("disconnected");
      });
      await page.waitForFunction(() => panel._addition?.phase === "stale");
      await page.evaluate(() => { fixture.connection.connected = true; fixture.event("ready"); });
      await page.getByRole("dialog").getByRole("button", { name: "Zavřít", exact: true }).click();
      await page.evaluate(() => { fixture.deferPreview = true; fixture.resolvePreview = null; });
      await page.getByRole("button", { name: "Přidat vybrané jako HA entity", exact: true }).click();
      await page.waitForFunction(() => Boolean(fixture.resolvePreview));
      await page.evaluate(() => {
        panel._plcs.value = "second"; panel._plcs.dispatchEvent(new Event("change")); fixture.resolvePreview();
      });
      await page.waitForFunction(() => panel._entryId === "second" && panel.model.runtime === "runtime-second");
      assert.equal(await page.evaluate(() => panel._addition), null);
      assert.equal(await page.getByRole("dialog").count(), 0);
      assert.equal(await page.evaluate(() => fixture.messages.some(m => m.type === "amit/monitor/confirm_add")), false);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("late previews cannot reopen canceled dialogs or cross PLCs; registry updates and disconnect invalidate confirmation");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak");
      await page.evaluate(() => { fixture.deferConfirm = true; fixture.confirmError = {}; fixture.emit(fixture.reading(4101, 27)); });
      await page.getByRole("button", { name: "Přidat vybrané jako HA entity", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("button", { name: "Uložit a načíst entity", exact: true }).click();
      await page.waitForFunction(() => panel._addition?.phase === "confirming");
      assert.equal(await dialog.getByRole("button", { name: "Zavřít", exact: true }).isDisabled(), true);
      await page.keyboard.press("Escape");
      assert.equal(await dialog.count(), 1);
      await page.evaluate(() => panel._confirmAddition());
      assert.equal(await page.evaluate(() => fixture.messages.filter(m => m.type === "amit/monitor/confirm_add").length), 1);
      await page.evaluate(() => { fixture.resolveConfirm(); fixture.deferConfirm = false; });
      await page.waitForFunction(() => panel._addition?.phase === "unknown");
      await dialog.getByText("Výsledek potvrzení nelze ověřit.", { exact: false }).waitFor();
      assert.ok((await dialog.textContent()).includes("Výběr mohl být uložen"));
      assert.equal(await page.evaluate(() => panel.model.count), 1);
      for (const [code, expected] of [["stale_preview", "stale"], ["expired_preview", "stale"], ["save_failed", "saveError"], ["busy", "saveError"]]) {
        await page.evaluate(code => { fixture.confirmError = { code }; }, code);
        await dialog.getByRole("button", { name: "Připravit nový náhled", exact: true }).click();
        await dialog.getByRole("button", { name: "Uložit a načíst entity", exact: true }).click();
        await page.waitForFunction(phase => panel._addition?.phase === phase, expected);
      }
      await page.evaluate(() => { fixture.confirmError = null; fixture.additionStatus = "failed"; });
      await dialog.getByRole("button", { name: "Připravit nový náhled", exact: true }).click();
      await dialog.getByRole("button", { name: "Uložit a načíst entity", exact: true }).click();
      await page.waitForFunction(() => panel._addition?.phase === "failed");
      await dialog.getByText("Výběr uložen, ale načtení selhalo.", { exact: false }).waitFor();
      assert.ok((await dialog.textContent()).includes("Výběr uložen, ale načtení selhalo"));
      await dialog.getByRole("button", { name: "Zavřít", exact: true }).click();
      await page.evaluate(() => panel.remove());
      const calls = await page.evaluate(() => fixture.messages.length);
      await page.waitForTimeout(2200);
      assert.equal(await page.evaluate(() => fixture.messages.length), calls);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("single confirmation in flight, unknown save outcome, stale/expired/busy/save errors, saved reload failure and close cleanup");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak");
      await page.evaluate(() => {
        fixture.preview = { preview_id: "noop-preview", expires_at: Math.floor(Date.now() / 1000) + 300,
          requested_wids: [4101], added_wids: [], already_configured_wids: [4101], newly_monitored_wids: [],
          removed_write_wids: [], selection_mode: "explicit", requires_reload: false,
          variables: fixture.snapshot("first").variables.filter(v => v.wid === 4101) };
        fixture.emit(fixture.reading(4101, 28));
      });
      await page.getByRole("button", { name: "Přidat vybrané jako HA entity", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByText("Vybrané proměnné už jsou nastavené.", { exact: false }).waitFor();
      assert.equal(await dialog.getByRole("button", { name: "Uložit a načíst entity", exact: true }).count(), 0);
      await page.keyboard.press("Escape");
      await page.waitForFunction(() => panel._addition === null);
      assert.equal(await page.evaluate(() => panel.model.count), 1);
      assert.equal(await page.evaluate(() => fixture.messages.some(m => m.type === "amit/monitor/confirm_add")), false);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("already configured selection has no save or reload action and preserves history");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak");
      await page.getByRole("button", { name: "Přidat vybrané jako HA entity", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("button", { name: "Uložit a načíst entity", exact: true }).click();
      await page.waitForFunction(() => panel._addition?.phase === "pending");
      await dialog.getByRole("button", { name: "Zavřít", exact: true }).click();
      await page.evaluate(() => fixture.visibility(true));
      const hiddenCalls = await page.evaluate(() => fixture.messages.length);
      await page.waitForTimeout(2200);
      assert.equal(await page.evaluate(() => fixture.messages.length), hiddenCalls);
      await page.evaluate(() => { fixture.statusError = {}; fixture.visibility(false); });
      await page.waitForFunction(() => panel._addition?.pollError === true);
      await page.evaluate(() => {
        fixture.connection = { ...fixture.connection };
        fixture.statusError = { code: "not_found" };
        panel.hass = { ...panel._hass, connection: fixture.connection };
      });
      await page.waitForFunction(() => panel._addition?.phase === "unknown");
      await page.locator("amit-monitor-panel .addition-status").getByText("Výsledek potvrzení nelze ověřit.", { exact: false }).waitFor();
      assert.equal(await page.evaluate(() => panel._addition.pollError), false);
      await page.getByRole("button", { name: "Přidat vybrané jako HA entity", exact: true }).click();
      await page.evaluate(() => { fixture.statusError = null; });
      await dialog.getByRole("button", { name: "Uložit a načíst entity", exact: true }).click();
      await page.waitForFunction(() => panel._addition?.phase === "pending");
      await page.evaluate(() => panel.remove());
      const closedCalls = await page.evaluate(() => fixture.messages.length);
      await page.waitForTimeout(2200);
      assert.equal(await page.evaluate(() => fixture.messages.length), closedCalls);
      assert.equal(await page.evaluate(() => panel._addition), null);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("pending operation polling stops while hidden and after close; replacement connections resume status checks; lost operation is an unknown outcome");
      await page.close();
    }
    {
      const { page, errors, requests } = await mount(browser);
      await select(page, "TE_obyvak");
      await page.getByRole("button", { name: "Přidat vybrané jako HA entity", exact: true }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Uložit a načíst entity", exact: true }).click();
      await page.waitForFunction(() => panel._addition?.phase === "pending");
      await page.getByRole("dialog").getByRole("button", { name: "Zavřít", exact: true }).click();
      await page.evaluate(() => {
        fixture.entries = [];
        for (const active of [...fixture.active.values()]) active.callback({ kind: "unavailable", runtime_id: "runtime-first" });
      });
      await page.waitForFunction(() => panel._unavailable && panel._entries.length === 0);
      await page.evaluate(() => {
        fixture.runtimeSuffix = "-reloaded";
        fixture.entries = [{ entry_id: "first", title: "Vytápění · Biosuntec" }];
      });
      await page.getByRole("button", { name: "Obnovit seznam PLC", exact: true }).click();
      await page.waitForFunction(() => panel.model.runtime === "runtime-first-reloaded");
      const before = await page.evaluate(() => {
        fixture.emit(fixture.reading(4101, 29));
        return { series: JSON.stringify([...panel.model.selected]), count: panel.model.count,
          latest: JSON.stringify([...panel.model.latest]), subscriptions: fixture.calls };
      });
      assert.equal(before.count, 1);
      await page.evaluate(async () => {
        fixture.additionStatus = "loaded";
        await panel._pollAddition();
      });
      await page.waitForFunction(() => panel._addition?.phase === "loaded");
      const after = await page.evaluate(() => ({ series: JSON.stringify([...panel.model.selected]), count: panel.model.count,
        latest: JSON.stringify([...panel.model.latest]), subscriptions: fixture.calls }));
      assert.deepEqual(after, before);
      await page.evaluate(() => fixture.emit(fixture.reading(4101, 30)));
      assert.equal(await page.evaluate(() => panel.model.count), 2);
      assert.equal(await page.evaluate(() => panel.model.selected.get(4101).points.at(-1).breakBefore), false);
      assert.deepEqual(errors, []); assert.deepEqual(requests, []);
      results.push("late reload success preserves fresh runtime history, latest values, subscription and uninterrupted subsequent samples");
      await page.close();
    }
    console.log(JSON.stringify({ passed: results }, null, 2));
  } finally { await browser.close(); }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
