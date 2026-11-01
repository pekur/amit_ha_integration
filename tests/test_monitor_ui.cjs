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
      { wid: 4501, name: "Program_tydne", type: "Array", unit: null, revision: 6, readable: false },
      { wid: 0, name: '<img src="bad" onerror="window.injected=true">', type: "Int", unit: null, revision: 7, readable: true },
    ];
    const fixture = window.fixture = {
      sequence: 10, variables, active: new Map(), pending: [], nextId: 1, calls: 0,
      entries: [{ entry_id: "first", title: "Vytápění · Biosuntec" }, { entry_id: "second", title: "Vzduchotechnika · Generic" }],
      listeners: new Map(), deferSubscription: Boolean(options.deferSubscription),
    };
    fixture.reading = (wid, value, status = "ok") => ({
      wid, value, status, sequence: ++fixture.sequence,
      revision: fixture.variables.find(v => v.wid === wid)?.revision,
      timestamp: new Date(Date.now() - 60000 + fixture.sequence * 1000).toISOString(),
    });
    fixture.snapshot = entry => ({ kind: "snapshot", runtime_id: `runtime-${entry}`, sequence: fixture.sequence,
      variables: fixture.variables.map(v => ({ ...v, configured: false, entities: [] })), scan_interval: 30,
      samples: [{ ...fixture.reading(4101, 22.4), sequence: fixture.sequence }],
    });
    fixture.connection = {
      connected: true,
      addEventListener(name, cb) { if (!fixture.listeners.has(name)) fixture.listeners.set(name, new Set()); fixture.listeners.get(name).add(cb); },
      removeEventListener(name, cb) { fixture.listeners.get(name)?.delete(cb); },
      async sendMessagePromise(message) { assertType(message.type, "amit/monitor/list"); return fixture.entries; },
      subscribeMessage(callback, message, opts) {
        assertType(message.type, "amit/monitor/subscribe");
        if (opts.resubscribe !== false) throw Error("Duplicate reconnect ownership");
        fixture.calls++;
        const id = fixture.nextId++;
        fixture.active.set(id, { callback, entry: message.entry_id });
        fixture.oldCallback = callback;
        callback(fixture.snapshot(message.entry_id));
        const unsubscribe = () => { fixture.active.delete(id); };
        return fixture.deferSubscription ? new Promise(resolve => fixture.pending.push(() => resolve(unsubscribe))) : Promise.resolve(unsubscribe);
      },
    };
    function assertType(actual, expected) { if (actual !== expected) throw Error(`Unexpected command ${actual}`); }
    fixture.emit = sample => { for (const active of fixture.active.values()) active.callback({ kind: "sample", runtime_id: `runtime-${active.entry}`, sample }); };
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
  await page.waitForFunction(name => [...panel.model.selected.keys()].some(wid => panel.model.catalog.get(wid).name === name), name);
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
            { entity_id: "sensor.renamed", name: "New name", custom_name: "New name", disabled: false },
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
    console.log(JSON.stringify({ passed: results }, null, 2));
  } finally { await browser.close(); }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
