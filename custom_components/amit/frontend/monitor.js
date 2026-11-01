/* AMiT Monitor. All session state lives only in this component's memory. */
export const TRANSLATIONS = {
  en: {
    title: "AMiT Monitor", plc: "PLC", variables: "Variables", trends: "Values over time",
    search: "Search name or WID…", type: "Variable type", allTypes: "All types",
    variable: "Name / WID / type", value: "Value / reading", selected: "Selected",
    pause: "Pause", resume: "Resume", clear: "Clear history", refresh: "Refresh PLC list",
    waiting: "Waiting for a reading", unsupported: "Reading not supported", read_error: "Read failed",
    invalid: "Invalid value", stale: "Stale", lastKnown: "Last valid", ago: "ago",
    second: "s", minute: "min", hour: "h", raw: "Raw PLC values · read only",
    empty: "No matching variables", choose: "Select variables in the table to start recording.",
    noSamples: "Waiting for a new sample", loading: "Loading PLCs…", noPlcs: "No loaded PLCs",
    unavailable: "This PLC is unavailable", offline: "Disconnected from Home Assistant",
    connected: "Connected to Home Assistant", paused: "Monitoring paused", hidden: "Monitoring suspended",
    error: "Unable to load the monitor. Try refreshing the PLC list.", admin: "Administrator access required",
    lastRead: "Last reading", page: "Page", previous: "Previous page", next: "Next page",
    sample: "Sample", samples: "samples", time: "Time", measurement: "Value", menu: "Open sidebar",
    memory: "History is cleared when you leave the monitor or change PLC. Memory only; up to 2,000 samples per variable and 50,000 in total. Oldest samples are removed at the limit.",
    limited: "The oldest samples have been removed to keep the memory limit.",
    snapshot: "Latest values are shown immediately when available; history starts with new readings.",
    haFilter: "Home Assistant entities", allVariables: "All variables", withEntity: "With HA entity",
    disabledEntity: "Disabled", configuredOnly: "Selected in HA configuration · no entity",
    plcVariable: "PLC variable",
    readInterval: "Reading interval (s)", intervalScope: "Apply interval to",
    intervalAll: "All readable variables", intervalSelected: "Selected variables only",
    intervalApply: "Apply", intervalReset: "Use device interval", intervalDevice: "Device interval",
    intervalRequested: "Requested interval", intervalActive: "Applied", intervalPending: "Inactive",
    intervalInvalid: "Enter a number from 1 to 120 seconds.", intervalFailed: "Unable to apply the interval. Try again or use the device interval.",
    intervalHelp: "Temporary for this panel. Selected means all variables checked for graphs, including filtered or paginated rows. Other variables use the device interval. Shared HA readings or another panel can update values faster; slow replies and large catalogs can delay them. Closing this panel releases its request.",
    addEntities: "Add selected as HA entities", addTitle: "Add variables to Home Assistant",
    addScope: "All selected variables are included, including those hidden by filters or on other pages.",
    addPreviewing: "Preparing preview…", addConfirm: "Save and load entities", cancel: "Cancel", close: "Close",
    addSelected: "Selected variables", addNew: "Added to configuration", addMonitored: "Newly monitored after reload",
    addExisting: "Already in configuration", addAll: "This device uses all readable variables. That setting stays enabled; reloading can add other variables shown below.",
    addReadOnly: "New variables are added for reading. Existing valid write permissions are preserved. No control values are written to the PLC.",
    addRemovedWrites: "Invalid write permissions to remove", addHistory: "Reloading clears the temporary monitor history. New entities use Home Assistant's normal history settings.",
    addConfirming: "Saving the selection…", addSaved: "Selection saved. Waiting for reload…",
    addReloading: "Selection saved. Loading entities…", addPending: "Selection saved. Home Assistant is waiting to retry loading the device.",
    addLoaded: "Selection saved and the device loaded successfully.", addUnchanged: "The selected variables are already configured. No reload is needed.",
    addFailed: "Selection saved, but loading failed. Check the integration in Home Assistant settings.",
    addStale: "The selection, device or entity information changed. Prepare a new preview.",
    addPreviewError: "Unable to prepare the preview. Refresh the PLC list and try again.",
    addSaveError: "The selection was not saved. Prepare a new preview and try again.",
    addBusy: "Another saved change is still loading. Wait for it to finish, then prepare a new preview.",
    addUnknown: "The confirmation result could not be verified. The selection may have been saved. Refresh the PLC list and prepare a new preview.",
    addStatusError: "Unable to check the saved change. The status will be checked again when the connection is available.",
    addRetry: "Prepare new preview", addDetails: "View details",
    addPreviewReady: "Check the preview before saving the selection.",
  },
  cs: {
    title: "AMiT Monitor", plc: "PLC", variables: "Proměnné", trends: "Sledování v čase",
    search: "Hledat název nebo WID…", type: "Typ proměnné", allTypes: "Všechny typy",
    variable: "Název / WID / typ", value: "Hodnota / odečet", selected: "Vybráno",
    pause: "Pozastavit", resume: "Pokračovat", clear: "Vymazat historii", refresh: "Obnovit seznam PLC",
    waiting: "Čeká na odečet", unsupported: "Čtení nepodporováno", read_error: "Chyba odečtu",
    invalid: "Neplatná hodnota", stale: "Zastaralé", lastKnown: "Poslední platná", ago: "před",
    second: "s", minute: "min", hour: "h", raw: "Surové hodnoty PLC · pouze čtení",
    empty: "Žádná odpovídající proměnná", choose: "Vyberte proměnné v přehledu pro zahájení záznamu.",
    noSamples: "Čeká na nový vzorek", loading: "Načítání PLC…", noPlcs: "Žádné načtené PLC",
    unavailable: "Toto PLC není dostupné", offline: "Odpojeno od Home Assistantu",
    connected: "Připojeno k Home Assistantu", paused: "Sledování pozastaveno", hidden: "Sledování uspáno",
    error: "Monitor se nepodařilo načíst. Zkuste obnovit seznam PLC.", admin: "Vyžaduje přístup administrátora",
    lastRead: "Poslední odečet", page: "Strana", previous: "Předchozí strana", next: "Další strana",
    sample: "Vzorek", samples: "vzorků", time: "Čas", measurement: "Hodnota", menu: "Otevřít postranní panel",
    memory: "Historie zanikne při opuštění monitoru nebo změně PLC. Pouze v paměti; nejvýše 2 000 vzorků na proměnnou a 50 000 celkem. Při dosažení limitu se odstraní nejstarší vzorky.",
    limited: "Nejstarší vzorky byly odstraněny kvůli limitu paměti.",
    snapshot: "Poslední hodnoty se zobrazí, pokud jsou dostupné; historie začíná novými odečty.",
    haFilter: "Entity Home Assistantu", allVariables: "Všechny proměnné", withEntity: "S HA entitou",
    disabledEntity: "Zakázaná", configuredOnly: "Vybraná v konfiguraci HA · bez entity",
    plcVariable: "Proměnná PLC",
    readInterval: "Interval čtení (s)", intervalScope: "Použít interval pro",
    intervalAll: "Všechny čitelné proměnné", intervalSelected: "Jen vybrané proměnné",
    intervalApply: "Použít", intervalReset: "Použít interval zařízení", intervalDevice: "Interval zařízení",
    intervalRequested: "Požadovaný interval", intervalActive: "Použito", intervalPending: "Neaktivní",
    intervalInvalid: "Zadejte číslo od 1 do 120 sekund.", intervalFailed: "Interval se nepodařilo použít. Zkuste to znovu nebo použijte interval zařízení.",
    intervalHelp: "Dočasně pro tento panel. Výběr zahrnuje všechny proměnné zaškrtnuté pro grafy, i skryté filtrem nebo na jiné stránce. Ostatní používají interval zařízení. Sdílené odečty HA nebo jiný panel mohou hodnoty obnovovat rychleji; pomalé odpovědi a velký katalog je mohou zpozdit. Zavřením panelu se jeho požadavek zruší.",
    addEntities: "Přidat vybrané jako HA entity", addTitle: "Přidat proměnné do Home Assistantu",
    addScope: "Zahrnuty jsou všechny vybrané proměnné, i ty skryté filtrem nebo na jiné stránce.",
    addPreviewing: "Připravuji náhled…", addConfirm: "Uložit a načíst entity", cancel: "Zrušit", close: "Zavřít",
    addSelected: "Vybrané proměnné", addNew: "Doplnění konfigurace", addMonitored: "Nově sledované po načtení",
    addExisting: "Již v konfiguraci", addAll: "Zařízení používá všechny čitelné proměnné. Toto nastavení zůstane zachováno; načtení může přidat i další níže uvedené proměnné.",
    addReadOnly: "Nové proměnné se přidají pro čtení. Stávající platná oprávnění k zápisu zůstanou zachována. Do PLC se nezapisují žádné řídicí hodnoty.",
    addRemovedWrites: "Neplatná oprávnění k zápisu k odebrání", addHistory: "Opětovné načtení vymaže dočasnou historii monitoru. Nové entity podléhají běžnému nastavení historie Home Assistantu.",
    addConfirming: "Ukládám výběr…", addSaved: "Výběr uložen. Čeká se na opětovné načtení…",
    addReloading: "Výběr uložen. Načítám entity…", addPending: "Výběr uložen. Home Assistant čeká na další pokus o načtení zařízení.",
    addLoaded: "Výběr uložen a zařízení úspěšně načteno.", addUnchanged: "Vybrané proměnné už jsou nastavené. Opětovné načtení není potřeba.",
    addFailed: "Výběr uložen, ale načtení selhalo. Zkontrolujte integraci v nastavení Home Assistantu.",
    addStale: "Výběr, zařízení nebo informace o entitách se změnily. Připravte nový náhled.",
    addPreviewError: "Náhled se nepodařilo připravit. Obnovte seznam PLC a zkuste to znovu.",
    addSaveError: "Výběr nebyl uložen. Připravte nový náhled a zkuste to znovu.",
    addBusy: "Jiná uložená změna se ještě načítá. Počkejte na dokončení a připravte nový náhled.",
    addUnknown: "Výsledek potvrzení nelze ověřit. Výběr mohl být uložen. Obnovte seznam PLC a připravte nový náhled.",
    addStatusError: "Stav uložené změny se nepodařilo ověřit. Po obnovení spojení jej zkusíme načíst znovu.",
    addRetry: "Připravit nový náhled", addDetails: "Zobrazit podrobnosti",
    addPreviewReady: "Před uložením výběru zkontrolujte náhled.",
  },
};

function entityFields(variable) {
  return {
    configured: variable.configured === true,
    entities: (Array.isArray(variable.entities) ? variable.entities : [])
      .filter(e => e && typeof e.entity_id === "string" && e.entity_id && typeof e.name === "string" && e.name)
      .map(e => ({ entity_id: e.entity_id, name: e.name,
        custom_name: typeof e.custom_name === "string" ? e.custom_name : null, disabled: e.disabled === true })),
  };
}

export class MonitorHistory {
  constructor(perVariable = 2000, total = 50000) {
    this.perVariable = perVariable;
    this.limit = total;
    this.catalog = new Map();
    this.latest = new Map();
    this.selected = new Map();
    this.runtime = null;
    this.sequence = 0;
    this.count = 0;
    this.interval = 30;
    this.intervals = new Map();
    this.trimmed = false;
  }

  snapshot(event) {
    if (this.runtime !== null && this.runtime !== event.runtime_id) {
      this.latest.clear();
      this.clearHistory();
      this.catalog.clear();
      this.sequence = 0;
    }
    this.runtime = event.runtime_id;
    this.interval = Number.isFinite(event.scan_interval) ? event.scan_interval : 30;
    const catalog = new Map(event.variables.map(v => [v.wid, { ...v, ...entityFields(v) }]));
    for (const [wid, series] of this.selected) {
      const variable = catalog.get(wid);
      if (!variable?.readable) {
        this.select(wid, false);
      } else if (this.catalog.get(wid)?.revision !== variable.revision) {
        this.count -= series.points.length;
        series.points = [];
      }
    }
    for (const [wid, value] of this.latest) {
      if (catalog.get(wid)?.revision !== value.revision) this.latest.delete(wid);
    }
    this.catalog = catalog;
    this.intervals.clear();
    this.updateIntervals(event);
    this.sequence = Math.max(this.sequence, event.sequence || 0);
    for (const sample of event.samples || []) this._latest(sample);
    // A snapshot can contain readings missed during a pause. They update the
    // table, but never backfill a graph or become new measurements.
    this.breakSeries();
    for (const series of this.selected.values()) series.floor = this.sequence;
  }

  entityMetadata(event) {
    if (event.runtime_id !== this.runtime || !Array.isArray(event.variables)) return;
    for (const patch of event.variables) {
      if (!patch || typeof patch.configured !== "boolean" || !Array.isArray(patch.entities)) continue;
      const variable = this.catalog.get(patch.wid);
      if (variable) this.catalog.set(patch.wid, { ...variable, ...entityFields(patch) });
    }
  }

  updateIntervals(event) {
    if (event.runtime_id !== this.runtime || !event.intervals || typeof event.intervals !== "object") return;
    this.intervals = new Map([...this.catalog.keys()].map(wid => {
      const value = event.intervals[wid];
      return [wid, Number.isFinite(value) && value > 0 ? value : this.interval];
    }));
  }

  readingInterval(wid) {
    return this.intervals.get(wid) ?? this.interval;
  }

  _latest(sample) {
    if (this.catalog.get(sample.wid)?.revision !== sample.revision) return false;
    if (!Number.isInteger(sample.sequence) || !Number.isFinite(Date.parse(sample.timestamp))) return false;
    if ((this.latest.get(sample.wid)?.sequence ?? -1) >= sample.sequence) return false;
    const normalized = { ...sample };
    if (sample.status === "ok" && !Number.isFinite(sample.value)) {
      normalized.status = "invalid";
      normalized.value = null;
    }
    this.latest.set(sample.wid, normalized);
    this.sequence = Math.max(this.sequence, sample.sequence);
    return true;
  }

  sample(event) {
    if (event.runtime_id !== this.runtime || !this._latest(event.sample)) return false;
    const sample = this.latest.get(event.sample.wid);
    const series = this.selected.get(sample.wid);
    if (!series || sample.sequence <= series.floor) return true;
    series.points.push({ ...sample, breakBefore: series.gap });
    series.floor = sample.sequence;
    series.gap = false;
    this.count++;
    if (series.points.length > this.perVariable) {
      this.count -= series.points.length - this.perVariable;
      series.points.splice(0, series.points.length - this.perVariable);
      this.trimmed = true;
    }
    while (this.count > this.limit) {
      let oldest;
      for (const value of this.selected.values()) {
        if (value.points.length && (!oldest || value.points[0].sequence < oldest.points[0].sequence)) oldest = value;
      }
      oldest.points.shift();
      this.count--;
      this.trimmed = true;
    }
    return true;
  }

  select(wid, selected) {
    if (selected && this.catalog.get(wid)?.readable && !this.selected.has(wid)) {
      this.selected.set(wid, { points: [], floor: this.sequence, gap: false });
    } else if (!selected && this.selected.has(wid)) {
      this.count -= this.selected.get(wid).points.length;
      this.selected.delete(wid);
    }
  }

  clearHistory() {
    for (const series of this.selected.values()) {
      series.points = [];
      series.floor = this.sequence;
      series.gap = false;
    }
    this.count = 0;
    this.trimmed = false;
  }

  breakSeries() {
    for (const series of this.selected.values()) series.gap = series.points.length > 0;
  }
}

const STYLE = `
:host{display:block;height:100%;overflow:auto;color:var(--primary-text-color,#182b3a);background:var(--primary-background-color,#f5f7fa);font:14px/1.5 var(--paper-font-body1_-_font-family,system-ui,sans-serif)}
*{box-sizing:border-box}h1,h2,p{margin:0}h1{font-size:22px;font-weight:500}h2{font-size:16px;font-weight:500}
header{padding:20px 24px;background:var(--card-background-color,#fff);border-bottom:1px solid var(--divider-color,#dce4eb)}
.heading,.meta,.section-head,.actions,.pager,.chart-head{display:flex;align-items:center;flex-wrap:wrap;gap:10px}.heading{margin-bottom:14px}.meta{gap:12px 20px}.muted{color:var(--secondary-text-color,#526775)}.small{font-size:12px}.number{font-variant-numeric:tabular-nums}
button,input,select{font:inherit;color:inherit}button,select,input[type=search]{border:1px solid var(--divider-color,#dce4eb);border-radius:7px;background:var(--card-background-color,#fff);padding:8px 10px;max-width:100%;min-width:0}button{cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px}button:hover{background:var(--secondary-background-color,#eef3f7)}button:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--primary-color,#007eaa);outline-offset:2px}button[aria-pressed=true]{background:var(--secondary-background-color,#eef3f7);border-color:var(--primary-color,#007eaa)}ha-icon{--mdc-icon-size:20px;width:20px;height:20px}label{max-width:100%}.menu{border:0;padding:8px}.meta select{max-width: min(100%,360px)}
.columns{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,1fr);align-items:start;gap:18px;padding:20px}.section{min-width:0;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce4eb);border-radius:12px;overflow:hidden}.section-head{padding:16px;justify-content:space-between}.tools,.actions{padding:0 16px 14px}.tools{display:flex;flex-wrap:wrap;gap:8px}.tools input{width:100%}.pager{padding:12px 16px;justify-content:space-between;border-top:1px solid var(--divider-color,#dce4eb)}.pager[hidden]{display:none}.pager button{padding:5px 9px}
table{width:100%;border-collapse:collapse}th{text-align:left;font-size:12px;font-weight:400;color:var(--secondary-text-color,#526775);background:var(--primary-background-color,#f5f7fa);padding:9px 10px}td{border-top:1px solid var(--divider-color,#dce4eb);padding:12px 10px;vertical-align:middle}td:first-child,th:first-child{width:42px;padding:0}td:first-child label{display:flex;align-items:center;justify-content:center;min-height:44px;min-width:42px}td:last-child,th:last-child{text-align:right}.name{display:block;overflow-wrap:anywhere;font-weight:500}.value{white-space:nowrap}input[type=checkbox]{width:18px;height:18px;accent-color:var(--primary-color,#007eaa)}tr.selected{background:color-mix(in srgb,var(--primary-color,#007eaa) 9%,var(--card-background-color,#fff))}.error{color:var(--error-color,#a12836)}.changed .value{animation:changed 1s ease-out}@keyframes changed{from{background:color-mix(in srgb,var(--primary-color,#007eaa) 25%,transparent)}to{background:transparent}}
.foot{padding:12px 16px;border-top:1px solid var(--divider-color,#dce4eb);color:var(--secondary-text-color,#526775);font-size:12px}.plots{padding:0 16px 12px}.chart{border-top:1px solid var(--divider-color,#dce4eb);padding-top:14px;margin-bottom:16px}.chart-head{justify-content:space-between}.chart-name{display:flex;align-items:center;gap:7px;min-width:0;overflow-wrap:anywhere}.swatch{width:18px;height:3px;background:var(--series);flex-shrink:0}.chart svg{display:block;width:100%;height:190px;touch-action:pan-y}.chart svg text{fill:var(--secondary-text-color,#526775);font:12px system-ui,sans-serif}.chart-detail{min-height:36px;font-size:12px;color:var(--secondary-text-color,#526775);overflow-wrap:anywhere}.sample-control{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--secondary-text-color,#526775)}.sample-control input{min-width:0;flex:1;accent-color:var(--primary-color,#007eaa)}.empty{padding:24px 16px;color:var(--secondary-text-color,#526775);text-align:center}.notice{padding:0 20px 20px;font-size:12px;color:var(--secondary-text-color,#526775)}.status{display:flex;align-items:center;gap:6px}.status-dot{width:8px;height:8px;border-radius:50%;background:var(--primary-color,#007eaa)}.status[data-offline=true] .status-dot{background:var(--disabled-text-color,#888)}.limit{padding:0 16px 12px;font-size:12px;color:var(--secondary-text-color,#526775)}[hidden]{display:none!important}
.identity,.entity-info{display:block;overflow-wrap:anywhere}.chart-name{flex:1}
.interval-settings{margin:16px 20px 0;padding:14px 16px;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce4eb);border-radius:12px}.interval-controls{display:flex;align-items:end;flex-wrap:wrap;gap:12px}.interval-controls label{display:flex;flex-direction:column;gap:4px}.interval-controls input{width:130px;border:1px solid var(--divider-color,#dce4eb);border-radius:7px;background:var(--card-background-color,#fff);padding:8px 10px}.interval-status{margin-top:10px}.interval-settings .small{margin-top:6px}
.addition-status{margin:16px 20px 0;padding:14px 16px;border:1px solid var(--divider-color,#dce4eb);border-radius:10px;background:var(--card-background-color,#fff);display:flex;align-items:center;justify-content:space-between;gap:12px;overflow-wrap:anywhere}.primary{background:color-mix(in srgb,var(--primary-color,#007eaa) 18%,var(--card-background-color,#fff));border-color:var(--primary-color,#007eaa);font-weight:500}button.primary:hover{background:color-mix(in srgb,var(--primary-color,#007eaa) 25%,var(--card-background-color,#fff))}
dialog{color:inherit;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce4eb);border-radius:14px;padding:20px;width:min(640px,calc(100vw - 24px));max-height:calc(100dvh - 32px);overflow:auto;box-shadow:0 16px 64px #0005}dialog::backdrop{background:#0007}dialog h2{font-size:20px}dialog .dialog-body{display:grid;gap:12px;margin:12px 0}dialog .dialog-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.addition-list{max-height:30vh;overflow:auto;border:1px solid var(--divider-color,#dce4eb);border-radius:8px}.addition-item{padding:9px 12px;overflow-wrap:anywhere}.addition-item+.addition-item{border-top:1px solid var(--divider-color,#dce4eb)}.addition-warning{padding:10px 12px;background:var(--secondary-background-color,var(--primary-background-color,#eef3f7));border-radius:8px}
:host([compact]) .columns{grid-template-columns:minmax(0,1fr)}
@media(max-width:600px){header{padding:14px}.columns{padding:14px;gap:14px;grid-template-columns:minmax(0,1fr)}.notice{padding:0 14px 18px}button{min-height:44px}select,input[type=search]{font-size:16px}h1{font-size:20px}}
@media(prefers-reduced-motion:reduce){.changed .value{animation:none}}
`;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

export class AMiTMonitorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.model = new MonitorHistory();
    this._entries = [];
    this._entryId = null;
    this._lang = "en";
    this._query = "";
    this._type = "all";
    this._haFilter = "all";
    this._tablePage = 0;
    this._chartPage = 0;
    this._rows = new Map();
    this._charts = new Map();
    this._token = 0;
    this._listToken = 0;
    this._paused = false;
    this._requestedInterval = null;
    this._intervalScope = "all";
    this._intervalError = null;
    this._intervalDraft = false;
    this._starting = false;
    this._subscriptionFailed = false;
    this._unavailable = false;
    this._loading = false;
    this._pageAway = false;
    this._addition = null;
    this._visibility = () => {
      this.model.breakSeries();
      if (document.hidden) this._stopSubscription();
      else this._sync();
      if (document.hidden) this._stopAdditionPoll(); else this._pollAddition();
      this._scheduleRender();
    };
    this._pageHide = () => { this._pageAway = true; this._endSession(); };
    this._pageShow = () => { this._pageAway = false; this._loadEntries(); };
    this._disconnected = () => {
      this._listToken++;
      this._loading = false;
      this.model.breakSeries();
      this._stopSubscription();
      this._invalidateAddition();
      this._stopAdditionPoll();
      this._scheduleRender();
    };
    this._ready = () => { this._subscriptionFailed = false; this._loadEntries(); this._pollAddition(); };
  }

  set hass(hass) {
    this._hass = hass;
    const lang = (hass.language || "en").split("-")[0] === "cs" ? "cs" : "en";
    const changed = lang !== this._lang;
    this._lang = lang;
    if (this.isConnected) {
      this._bindConnection();
      if (changed) this._translate();
      this._sync();
    }
  }

  connectedCallback() {
    if (!this.shadowRoot.firstChild) this._mount();
    document.addEventListener("visibilitychange", this._visibility);
    window.addEventListener("pagehide", this._pageHide);
    window.addEventListener("pageshow", this._pageShow);
    this._resize = new ResizeObserver(() => {
      this.toggleAttribute("compact", this.clientWidth < 760);
      this._scheduleRender();
    });
    this._resize.observe(this);
    this._clock = setInterval(() => this._scheduleRender(), 1000);
    this._bindConnection();
    this._translate();
    this._scheduleRender();
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._visibility);
    window.removeEventListener("pagehide", this._pageHide);
    window.removeEventListener("pageshow", this._pageShow);
    this._unbindConnection();
    this._resize?.disconnect();
    clearInterval(this._clock);
    clearTimeout(this._renderTimer);
    this._renderTimer = null;
    this._endSession();
  }

  _endSession() {
    this._resetAddition();
    this._stopSubscription();
    this._listToken++;
    this._loading = false;
    this.model = new MonitorHistory();
    this._resetInterval();
    this._entryId = null;
    this._entries = [];
    this._paused = false;
    this._query = "";
    this._type = "all";
    this._haFilter = "all";
    this._tablePage = this._chartPage = 0;
    this._subscriptionFailed = this._unavailable = false;
    this._error = null;
    this._rows.clear();
    this._charts.clear();
    this._tbody?.replaceChildren();
    this._plots?.replaceChildren();
    this._plcs?.replaceChildren();
    this._optionKey = null;
    if (this._search) this._search.value = "";
    if (this._filter) this._filter.value = "all";
    if (this._haSelect) this._haSelect.value = "all";
    if (this.isConnected) this._scheduleRender();
  }

  _bindConnection() {
    const connection = this._hass?.connection;
    if (!connection || this._connection === connection) return;
    this._unbindConnection();
    this._connection = connection;
    connection.addEventListener("disconnected", this._disconnected);
    connection.addEventListener("ready", this._ready);
    this._subscriptionFailed = false;
    this._loadEntries();
    this._pollAddition();
  }

  _unbindConnection() {
    this._invalidateAddition();
    this._stopAdditionPoll();
    this._stopSubscription();
    this._listToken++;
    this._loading = false;
    this.model.breakSeries();
    if (this._connection) {
      this._connection.removeEventListener("disconnected", this._disconnected);
      this._connection.removeEventListener("ready", this._ready);
    }
    this._connection = null;
  }

  async _loadEntries() {
    if (!this.isConnected || this._pageAway || !this._connection?.connected) return;
    const token = ++this._listToken;
    this._loading = true;
    this._scheduleRender();
    try {
      const entries = await this._connection.sendMessagePromise({ type: "amit/monitor/list" });
      if (token !== this._listToken || !this.isConnected) return;
      this._entries = entries;
      if (this._entryId === null && entries.length) this._entryId = entries[0].entry_id;
      this._unavailable = this._entryId !== null && !entries.some(e => e.entry_id === this._entryId);
      this._error = null;
      this._sync();
    } catch (error) {
      if (token === this._listToken) this._error = error?.code === "unauthorized" ? "admin" : "error";
    } finally {
      if (token === this._listToken) {
        this._loading = false;
        this._scheduleRender();
      }
    }
  }

  _safeUnsubscribe(unsubscribe) {
    // HA may already have removed a subscription when its PLC was unloaded.
    Promise.resolve().then(unsubscribe).catch(() => {});
  }

  _stopSubscription() {
    this._token++;
    this._starting = false;
    if (this._unsubscribe) this._safeUnsubscribe(this._unsubscribe);
    this._unsubscribe = null;
  }

  _sync() {
    if (!this.isConnected || !this._connection?.connected || !this._entryId ||
        this._paused || this._pageAway || document.hidden || this._unavailable) {
      if (this._starting || this._unsubscribe) this._stopSubscription();
      return;
    }
    if (this._starting || this._unsubscribe || this._subscriptionFailed) return;
    const token = ++this._token;
    this._starting = true;
    const receive = event => {
      if (token !== this._token || !this.isConnected || this._paused || document.hidden) return;
      if (event.kind === "snapshot" || event.kind === "catalog") {
        this.model.snapshot(event);
        if (!this._intervalDraft && this._requestedInterval === null) this._intervalInput.value = String(this.model.interval);
        this._checkAddition();
        if (this._requestedInterval !== null && this._intervalScope === "selected") {
          const key = JSON.stringify(this._intervalOptions());
          // A catalog can remove selected WIDs. Replace this subscription after
          // its acknowledgement without losing the browser's history.
          if (key !== requestKey) queueMicrotask(() => {
            if (token === this._token) this._restartInterval();
          });
        }
      } else if (event.kind === "intervals") {
        this.model.updateIntervals(event);
      } else if (event.kind === "entity_metadata") {
        this.model.entityMetadata(event);
        this._checkAddition();
      } else if (event.kind === "sample") {
        const previous = this.model.latest.get(event.sample.wid);
        if (this.model.sample(event) && previous?.value !== event.sample.value) {
          const row = this._rows.get(event.sample.wid)?.row;
          if (row) { row.classList.remove("changed"); void row.offsetWidth; row.classList.add("changed"); }
        }
      } else if (event.kind === "unavailable") {
        this._invalidateAddition();
        this._unavailable = true;
        this.model.breakSeries();
        this._stopSubscription();
        this._loadEntries();
      }
      this._scheduleRender();
    };
    const options = this._intervalOptions(), requestKey = JSON.stringify(options);
    this._connection.subscribeMessage(receive,
      { type: "amit/monitor/subscribe", entry_id: this._entryId, ...options }, { resubscribe: false })
      .then(unsubscribe => {
        if (token !== this._token || !this.isConnected) this._safeUnsubscribe(unsubscribe);
        else {
          this._unsubscribe = unsubscribe;
          this._starting = false;
          if (this._intervalError === "intervalFailed") this._intervalError = null;
          this._scheduleRender();
        }
      })
      .catch(error => {
        if (token !== this._token) return;
        this._starting = false;
        this._subscriptionFailed = true;
        if (this._requestedInterval !== null) this._intervalError = "intervalFailed";
        this._error = error?.code === "unauthorized" ? "admin" : "error";
        if (error?.code === "not_found") { this._unavailable = true; this._loadEntries(); }
        this._scheduleRender();
      });
  }

  _t(key) { return TRANSLATIONS[this._lang][key]; }

  _intervalOptions() {
    if (this._requestedInterval === null) return {};
    return { interval: this._requestedInterval, ...(this._intervalScope === "selected" ?
      { wids: [...this.model.selected.keys()].sort((a, b) => a - b) } : {}) };
  }

  _resetInterval() {
    this._requestedInterval = null;
    this._intervalScope = "all";
    this._intervalError = null;
    this._intervalDraft = false;
    if (this._intervalInput) this._intervalInput.value = String(this.model.interval);
    this._intervalInput?.removeAttribute("aria-invalid");
    if (this._scopeInput) this._scopeInput.value = "all";
  }

  _restartInterval() {
    this._subscriptionFailed = false;
    this._error = null;
    this._stopSubscription();
    this._sync();
    this._scheduleRender();
  }

  _mount() {
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <header><div class="heading"><button class="menu" type="button" data-label="menu"><ha-icon icon="mdi:menu"></ha-icon></button><h1>AMiT Monitor</h1></div>
      <div class="meta"><label><span data-text="plc"></span> <select class="plcs" data-label="plc"></select></label>
      <span class="status" role="status"><span class="status-dot"></span><span class="status-text"></span></span>
      <button type="button" class="refresh" data-label="refresh"><ha-icon icon="mdi:refresh"></ha-icon></button>
      <span class="last-read muted small"></span></div></header>
      <section class="interval-settings" data-label="readInterval"><form class="interval-controls" novalidate>
      <label><span data-text="readInterval"></span><input class="read-interval" type="number" min="1" max="120" step="any" required data-label="readInterval" aria-describedby="interval-help interval-error"></label>
      <label><span data-text="intervalScope"></span><select class="interval-scope" data-label="intervalScope"><option value="all" data-text="intervalAll"></option><option value="selected" data-text="intervalSelected"></option></select></label>
      <button type="submit" class="interval-apply" data-text="intervalApply"></button><button type="button" class="interval-reset" data-text="intervalReset"></button></form>
      <p class="interval-status number" role="status" aria-live="polite"></p><p id="interval-error" class="interval-error error" role="alert" hidden></p><p id="interval-help" class="small muted" data-text="intervalHelp"></p></section>
      <div class="addition-status" hidden><span role="status" aria-live="polite"></span><button type="button" class="addition-details" data-text="addDetails"></button></div>
      <div class="columns"><section class="section"><div class="section-head"><h2 data-text="variables"></h2><span class="count muted small"></span></div>
      <div class="tools"><input type="search" data-label="search"><select class="filter" data-label="type"></select><select class="ha-filter" data-label="haFilter"></select></div>
      <table><thead><tr><th><span aria-hidden="true">✓</span></th><th data-text="variable" scope="col"></th><th data-text="value" scope="col"></th></tr></thead><tbody></tbody></table>
      <div class="table-empty empty" data-text="empty" hidden></div><div class="table-pager pager"></div><div class="foot" data-text="raw"></div></section>
      <section class="section"><div class="section-head"><h2 data-text="trends"></h2><span class="selection muted small" aria-live="polite"></span></div>
      <div class="actions"><button class="pause" type="button" aria-pressed="false"></button><button class="clear" type="button" data-text="clear"></button><button class="add-entities" type="button" data-text="addEntities"></button></div>
      <div class="plots"></div><div class="chart-pager pager"></div><div class="limit" data-text="limited" hidden></div><div class="foot" data-text="snapshot"></div></section></div>
      <p class="notice" data-text="memory"></p>
      <dialog class="addition-dialog" aria-labelledby="addition-title"><h2 id="addition-title" data-text="addTitle"></h2><p class="addition-dialog-status" role="status" aria-live="polite"></p><div class="dialog-body"></div><div class="dialog-actions"><button class="addition-cancel" type="button"></button><button class="addition-retry" type="button" data-text="addRetry"></button><button class="addition-confirm primary" type="button" data-text="addConfirm"></button></div></dialog>`;
    const find = selector => this.shadowRoot.querySelector(selector);
    this._search = find("input[type=search]");
    this._filter = find(".filter");
    this._haSelect = find(".ha-filter");
    this._plcs = find(".plcs");
    this._intervalInput = find(".read-interval");
    this._scopeInput = find(".interval-scope");
    this._intervalInput.oninput = () => { this._intervalDraft = true; };
    find(".interval-controls").onsubmit = event => {
      event.preventDefault();
      const interval = this._intervalInput.valueAsNumber;
      if (!this._intervalInput.checkValidity() || !Number.isFinite(interval) || interval < 1 || interval > 120) {
        this._intervalError = "intervalInvalid";
        this._intervalInput.setAttribute("aria-invalid", "true");
        this._scheduleRender();
        return;
      }
      this._intervalInput.removeAttribute("aria-invalid");
      this._intervalError = null;
      this._requestedInterval = interval;
      this._intervalScope = this._scopeInput.value;
      this._restartInterval();
    };
    find(".interval-reset").onclick = () => {
      this._resetInterval();
      this._restartInterval();
    };
    this._tbody = find("tbody");
    this._plots = find(".plots");
    this._additionDialog = find(".addition-dialog");
    find(".add-entities").onclick = () => this._startAddition();
    find(".addition-confirm").onclick = () => this._confirmAddition();
    find(".addition-retry").onclick = () => this._startAddition();
    find(".addition-details").onclick = () => this._additionDialog.showModal();
    find(".addition-cancel").onclick = () => this._additionDialog.close();
    this._additionDialog.oncancel = event => { if (this._addition?.phase === "confirming") event.preventDefault(); };
    this._additionDialog.onclose = () => {
      if (!this._additionDialog.open && ["previewing", "preview", "stale", "previewError"].includes(this._addition?.phase)) this._resetAddition();
    };
    find(".menu").onclick = () => this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
    find(".refresh").onclick = () => { this._subscriptionFailed = false; this._loadEntries(); };
    this._search.oninput = () => { this._query = this._search.value.toLocaleLowerCase(); this._tablePage = 0; this._scheduleRender(); };
    this._filter.onchange = () => { this._type = this._filter.value; this._tablePage = 0; this._scheduleRender(); };
    this._haSelect.onchange = () => { this._haFilter = this._haSelect.value; this._tablePage = 0; this._scheduleRender(); };
    this._plcs.onchange = () => {
      this._resetAddition();
      this._stopSubscription();
      this._entryId = this._plcs.value || null;
      this.model = new MonitorHistory();
      this._resetInterval();
      this._paused = this._subscriptionFailed = this._unavailable = false;
      this._error = null;
      this._tablePage = this._chartPage = 0;
      this._sync();
      this._scheduleRender();
    };
    find(".pause").onclick = () => {
      this._paused = !this._paused;
      this.model.breakSeries();
      if (this._paused) this._stopSubscription(); else this._sync();
      this._scheduleRender();
    };
    find(".clear").onclick = () => { this.model.clearHistory(); this._scheduleRender(); };
  }

  _translate() {
    if (!this._search) return;
    this.shadowRoot.querySelectorAll("[data-text]").forEach(e => { e.textContent = this._t(e.dataset.text); });
    this.shadowRoot.querySelectorAll("[data-label]").forEach(e => { e.setAttribute("aria-label", this._t(e.dataset.label)); });
    this._search.placeholder = this._t("search");
    this._filter.replaceChildren(...["all", "Float", "Int", "Long", "Array", "TimeArray", "Structure", "Unknown"].map(value => {
      const option = node("option", "", value === "all" ? this._t("allTypes") : value);
      option.value = value;
      return option;
    }));
    this._filter.value = this._type;
    this._haSelect.replaceChildren(...["all", "ha"].map(value => {
      const option = node("option", "", this._t(value === "all" ? "allVariables" : "withEntity"));
      option.value = value;
      return option;
    }));
    this._haSelect.value = this._haFilter;
    this._scheduleRender();
  }

  _scheduleRender() {
    if (!this.isConnected || this._renderTimer) return;
    this._renderTimer = setTimeout(() => { this._renderTimer = null; this._render(); }, 100);
  }

  _format(value) {
    if (!Number.isFinite(value)) return "—";
    const magnitude = Math.abs(value);
    const scientific = magnitude >= 1e12 || (magnitude > 0 && magnitude < .00001);
    const format = scientific ? { notation: "scientific", maximumSignificantDigits: 9 } :
      Number.isInteger(value) ? { maximumFractionDigits: 0 } : { maximumSignificantDigits: 9 };
    return new Intl.NumberFormat(this._lang, format).format(value);
  }

  _axisLabels(min, max) {
    const values = [max, max - (max - min) / 2, min];
    const magnitude = Math.max(Math.abs(min), Math.abs(max));
    const notation = magnitude >= 1e6 || (magnitude > 0 && magnitude < .01) ? "scientific" : "standard";
    let labels;
    // Select precision for the whole scale, keeping each distinct tick legible.
    for (let precision = 3; precision <= 17; precision++) {
      const format = new Intl.NumberFormat(this._lang, { notation, maximumSignificantDigits: precision });
      labels = values.map(value => format.format(value));
      if (new Set(labels).size === values.length) break;
    }
    return labels;
  }

  _time(timestamp) {
    if (!timestamp || !Number.isFinite(Date.parse(timestamp))) return "—";
    return new Intl.DateTimeFormat(this._lang, { hour: "2-digit", minute: "2-digit", second: "2-digit",
      ...(this._hass?.config?.time_zone ? { timeZone: this._hass.config.time_zone } : {}) }).format(new Date(timestamp));
  }

  _age(timestamp) {
    const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(timestamp)) / 1000));
    if (!Number.isFinite(seconds)) return "—";
    const amount = seconds < 60 ? seconds : seconds < 3600 ? Math.floor(seconds / 60) : Math.floor(seconds / 3600);
    const unit = this._t(seconds < 60 ? "second" : seconds < 3600 ? "minute" : "hour");
    return this._lang === "cs" ? `${this._t("ago")} ${amount} ${unit}` : `${amount} ${unit} ${this._t("ago")}`;
  }

  _render() {
    if (!this._tbody) return;
    const find = selector => this.shadowRoot.querySelector(selector);
    const options = this._entries.map(entry => {
      const option = node("option", "", entry.title); option.value = entry.entry_id; return option;
    });
    if (this._unavailable && this._entryId) {
      const option = node("option", "", this._t("unavailable")); option.value = this._entryId; options.unshift(option);
    } else if (!options.length) options.push(node("option", "", this._t("noPlcs")));
    // Do not replace an open native picker on every arriving sample.
    const optionKey = JSON.stringify(options.map(e => [e.value, e.textContent]));
    if (this._optionKey !== optionKey) { this._plcs.replaceChildren(...options); this._optionKey = optionKey; }
    this._plcs.value = this._entryId || this._plcs.options[0]?.value || "";
    const status = this._error || (!this._connection?.connected ? "offline" : this._paused ? "paused" :
      document.hidden || this._pageAway ? "hidden" : this._unavailable ? "unavailable" :
      this._loading ? "loading" : !this._entries.length ? "noPlcs" : "connected");
    find(".status-text").textContent = this._t(status);
    find(".status").dataset.offline = String(status !== "connected");
    let latestTime;
    for (const sample of this.model.latest.values()) if (!latestTime || sample.timestamp > latestTime) latestTime = sample.timestamp;
    find(".last-read").textContent = `${this._t("lastRead")}: ${this._time(latestTime)}`;
    const pause = find(".pause");
    pause.textContent = this._t(this._paused ? "resume" : "pause");
    pause.setAttribute("aria-pressed", String(this._paused));
    pause.disabled = !this._entryId;
    find(".selection").textContent = `${this._t("selected")} ${this.model.selected.size}`;
    find(".limit").hidden = !this.model.trimmed;
    const custom = this._requestedInterval !== null;
    const scope = this._t(this._intervalScope === "selected" ? "intervalSelected" : "intervalAll");
    const applied = this._unsubscribe && !this._starting && !this._subscriptionFailed;
    find(".interval-status").textContent = `${this._t("intervalDevice")}: ${this._format(this.model.interval)} s` +
      (custom ? ` · ${this._t("intervalRequested")}: ${this._format(this._requestedInterval)} s · ${scope}${this._intervalScope === "selected" ? ` (${this.model.selected.size})` : ""} · ${this._t(applied ? "intervalActive" : "intervalPending")}` : "");
    find(".interval-error").textContent = this._intervalError ? this._t(this._intervalError) : "";
    find(".interval-error").hidden = !this._intervalError;
    find(".interval-apply").disabled = !this._entryId || this._unavailable;
    find(".interval-reset").disabled = !this._entryId;
    this._renderRows();
    this._renderCharts();
    this._renderAddition();
  }

  _additionBinding() {
    return JSON.stringify([this.model.runtime, [...this.model.selected.keys()], [...this.model.catalog.values()]]);
  }

  _additionBusy() {
    return ["previewing", "confirming", "saved", "reloading", "pending"].includes(this._addition?.phase);
  }

  _stopAdditionPoll() {
    clearTimeout(this._additionTimer);
    this._additionTimer = null;
    this._additionPollRequest = null;
  }

  _resetAddition() {
    this._stopAdditionPoll();
    this._addition = null;
    this._additionRenderKey = null;
    this._additionDialog?.close();
    this._scheduleRender();
  }

  _invalidateAddition() {
    if (["previewing", "preview"].includes(this._addition?.phase)) {
      this._addition.phase = "stale";
      this._addition.preview = null;
      this._scheduleRender();
    }
  }

  _checkAddition() {
    if (this._addition && this._addition.binding !== this._additionBinding()) this._invalidateAddition();
  }

  async _startAddition() {
    if (this._additionBusy() || !this._connection?.connected || this._unavailable || !this.model.runtime || !this.model.selected.size) return;
    this._stopAdditionPoll();
    this._additionRenderKey = null;
    const addition = this._addition = {
      entryId: this._entryId, title: this._entries.find(e => e.entry_id === this._entryId)?.title || this._t("plc"),
      runtime: this.model.runtime, binding: this._additionBinding(), phase: "previewing",
      variables: [...this.model.selected.keys()].map(wid => ({ wid, revision: this.model.catalog.get(wid).revision })),
    };
    this._renderAddition();
    if (!this._additionDialog.open) this._additionDialog.showModal();
    const connection = this._connection;
    try {
      const preview = await connection.sendMessagePromise({ type: "amit/monitor/preview_add",
        entry_id: addition.entryId, runtime_id: addition.runtime, variables: addition.variables });
      if (this._addition !== addition || addition.phase !== "previewing" || connection !== this._connection) return;
      this._checkAddition();
      if (addition.phase !== "previewing") return;
      addition.preview = preview;
      addition.phase = "preview";
    } catch (error) {
      if (this._addition === addition && addition.phase === "previewing") {
        addition.phase = "previewError";
        addition.error = error?.code === "unauthorized" ? "admin" : "addPreviewError";
      }
    }
    this._scheduleRender();
  }

  async _confirmAddition() {
    this._checkAddition();
    const addition = this._addition;
    if (addition?.phase !== "preview" || !addition.preview.requires_reload || !this._connection?.connected) return;
    addition.phase = "confirming";
    this._renderAddition();
    try {
      const result = await this._connection.sendMessagePromise({ type: "amit/monitor/confirm_add",
        entry_id: addition.entryId, runtime_id: addition.runtime, variables: addition.variables,
        preview_id: addition.preview.preview_id, expires_at: addition.preview.expires_at });
      if (this._addition !== addition) return;
      addition.phase = result.status;
      addition.operation = result;
      this._pollAddition();
    } catch (error) {
      if (this._addition !== addition) return;
      const code = error?.code;
      addition.phase = ["stale_selection", "stale_preview", "expired_preview", "invalid_selection", "not_found"].includes(code) ? "stale" :
        ["save_failed", "busy", "unauthorized", "invalid_configuration"].includes(code) ? "saveError" : "unknown";
      addition.error = code === "unauthorized" ? "admin" : code === "busy" ? "addBusy" : "addSaveError";
    }
    this._scheduleRender();
  }

  async _pollAddition() {
    clearTimeout(this._additionTimer);
    this._additionTimer = null;
    const addition = this._addition, connection = this._connection;
    if (!addition?.operation?.operation_id || !["saved", "reloading", "pending"].includes(addition.phase) ||
        !this.isConnected || this._pageAway || document.hidden || !connection?.connected || this._additionPollRequest) return;
    const request = this._additionPollRequest = {};
    try {
      const result = await connection.sendMessagePromise({ type: "amit/monitor/addition_status",
        entry_id: addition.entryId, operation_id: addition.operation.operation_id });
      if (this._additionPollRequest !== request || this._addition !== addition || connection !== this._connection) return;
      addition.operation = result;
      addition.phase = result.status;
      addition.pollError = false;
      if (result.status === "loaded") {
        // A new runtime snapshot already cleared the old history. Keep any
        // readings collected since then when the reload result arrives late.
        if (this.model.runtime === addition.runtime) {
          this.model.clearHistory();
          this.model.latest.clear();
          this._stopSubscription();
        }
        this._subscriptionFailed = false;
        await this._loadEntries();
      }
    } catch (error) {
      if (this._additionPollRequest !== request || this._addition !== addition) return;
      if (["not_found", "unauthorized"].includes(error?.code)) {
        addition.phase = "unknown";
        addition.pollError = false;
      }
      else addition.pollError = true;
    } finally {
      if (this._additionPollRequest === request) {
        this._additionPollRequest = null;
        if (this._addition === addition && ["saved", "reloading", "pending"].includes(addition.phase) &&
            this.isConnected && !this._pageAway && !document.hidden && connection.connected) {
          this._additionTimer = setTimeout(() => this._pollAddition(), 2000);
        }
        this._scheduleRender();
      }
    }
  }

  _renderAddition() {
    if (!this._additionDialog) return;
    const find = selector => this.shadowRoot.querySelector(selector), addition = this._addition;
    find(".add-entities").disabled = this._additionBusy() || !this.model.selected.size || !this.model.runtime ||
      !this._connection?.connected || this._unavailable;
    find(".addition-status").hidden = !addition || ["previewing", "preview"].includes(addition.phase);
    if (!addition) return;
    const keys = { previewing: "addPreviewing", preview: "addTitle", confirming: "addConfirming", saved: "addSaved",
      reloading: "addReloading", pending: "addPending", loaded: "addLoaded", unchanged: "addUnchanged", failed: "addFailed",
      stale: "addStale", unknown: "addUnknown", previewError: addition.error, saveError: addition.error };
    const message = this._t(addition.pollError ? "addStatusError" : keys[addition.phase]);
    find(".addition-status [role=status]").textContent = `${addition.title}: ${message}`;
    const status = find(".addition-dialog-status");
    status.textContent = addition.phase === "preview" ? this._t("addPreviewReady") : message;
    status.className = `addition-dialog-status ${["failed", "unknown", "stale", "previewError", "saveError"].includes(addition.phase) ? "error" : "muted"}`;
    const cancel = find(".addition-cancel"), confirm = find(".addition-confirm"), retry = find(".addition-retry");
    cancel.textContent = this._t(["previewing", "preview"].includes(addition.phase) ? "cancel" : "close");
    cancel.disabled = addition.phase === "confirming";
    confirm.hidden = addition.phase !== "preview" || !addition.preview?.requires_reload;
    retry.hidden = !["stale", "previewError", "saveError", "unknown"].includes(addition.phase);
    retry.disabled = !this._connection?.connected || this._unavailable || !this.model.selected.size;
    const key = JSON.stringify([this._lang, addition.phase, addition.preview, addition.pollError, addition.error]);
    if (this._additionRenderKey === key) return;
    this._additionRenderKey = key;
    const body = find(".dialog-body");
    body.replaceChildren(node("p", "name", addition.title));
    if (addition.phase !== "preview") return;
    const preview = addition.preview;
    body.append(node("p", "small muted", this._t("addScope")),
      node("p", "number", `${this._t("addSelected")}: ${preview.requested_wids.length} · ${this._t("addNew")}: ${preview.added_wids.length} · ${this._t("addExisting")}: ${preview.already_configured_wids.length}`),
      node("p", "number", `${this._t("addMonitored")}: ${preview.newly_monitored_wids.length}`));
    if (preview.selection_mode === "all") body.append(node("p", "addition-warning", this._t("addAll")));
    const list = node("div", "addition-list");
    list.setAttribute("role", "list");
    for (const item of preview.variables) {
      const variable = { ...item, ...entityFields(item) }, row = node("div", "addition-item");
      row.setAttribute("role", "listitem");
      row.append(node("span", "name", this._variableName(variable)),
        node("span", "small muted identity", `${this._t("plcVariable")}: ${variable.name} · WID ${variable.wid} · ${variable.type}`));
      if (variable.entities.length) row.append(node("span", "small muted identity", this._entityInfo(variable)));
      list.append(row);
    }
    body.append(list, node("p", "small", this._t("addReadOnly")));
    if (preview.removed_write_wids.length) body.append(node("p", "addition-warning small",
      `${this._t("addRemovedWrites")}: ${preview.removed_write_wids.map(wid => `WID ${wid}`).join(", ")}`));
    body.append(node("p", preview.requires_reload ? "addition-warning" : "muted",
      this._t(preview.requires_reload ? "addHistory" : "addUnchanged")));
  }

  _pager(element, page, count, size, update) {
    const pages = Math.max(1, Math.ceil(count / size));
    element.hidden = pages === 1;
    if (!element.firstChild) element.append(node("button", "", "‹"), node("span", "small muted"), node("button", "", "›"));
    const [previous, label, next] = element.children;
    previous.type = next.type = "button";
    previous.setAttribute("aria-label", this._t("previous")); next.setAttribute("aria-label", this._t("next"));
    previous.disabled = page === 0; next.disabled = page >= pages - 1;
    previous.onclick = () => { update(page - 1); this._scheduleRender(); };
    next.onclick = () => { update(page + 1); this._scheduleRender(); };
    label.textContent = `${this._t("page")} ${page + 1} / ${pages}`;
  }

  _variableName(variable) {
    return [...new Set(variable.entities.map(e => e.name))].join(" · ") || variable.name;
  }

  _variableIdentity(variable) {
    return `${variable.entities.length ? this._t("plcVariable") + ": " + variable.name + " · " : ""}WID ${variable.wid} · ${variable.type}`;
  }

  _entityInfo(variable) {
    return variable.entities.map(e => `${variable.entities.length > 1 ? e.name + " · " : ""}${e.entity_id}${e.disabled ? " · " + this._t("disabledEntity") : ""}`)
      .join("; ") || (variable.configured ? this._t("configuredOnly") : "");
  }

  _renderRows() {
    const variables = [...this.model.catalog.values()].filter(v =>
      ([v.name, String(v.wid), ...v.entities.map(e => e.name)].some(name => name.toLocaleLowerCase().includes(this._query))) &&
      (this._type === "all" || v.type === this._type) && (this._haFilter === "all" || v.entities.length > 0));
    this._tablePage = Math.min(this._tablePage, Math.max(0, Math.ceil(variables.length / 50) - 1));
    const visible = variables.slice(this._tablePage * 50, (this._tablePage + 1) * 50);
    const keep = new Set(visible.map(v => v.wid));
    for (const [wid, entry] of this._rows) if (!keep.has(wid)) { entry.row.remove(); this._rows.delete(wid); }
    let nextRow = this._tbody.firstChild;
    for (const variable of visible) {
      let entry = this._rows.get(variable.wid);
      if (!entry) {
        const row = node("tr"), checkCell = node("td"), label = node("label"), checkbox = node("input");
        checkbox.type = "checkbox";
        checkbox.onchange = () => {
          this.model.select(variable.wid, checkbox.checked);
          this._checkAddition();
          if (this._requestedInterval !== null && this._intervalScope === "selected") this._restartInterval();
          this._scheduleRender();
        };
        label.append(checkbox); checkCell.append(label);
        const nameCell = node("td"), name = node("span", "name"), metadata = node("span", "identity small muted"), entities = node("div", "entity-info small muted");
        nameCell.append(name, metadata, entities);
        const valueCell = node("td"), value = node("span", "number value"), reading = node("div", "small"), last = node("div", "small muted");
        valueCell.append(value, reading, last); row.append(checkCell, nameCell, valueCell);
        entry = { row, checkbox, name, metadata, entities, value, reading, last };
        this._rows.set(variable.wid, entry);
      }
      if (entry.row !== nextRow) this._tbody.insertBefore(entry.row, nextRow);
      nextRow = entry.row.nextSibling;
      entry.checkbox.checked = this.model.selected.has(variable.wid);
      entry.checkbox.disabled = !variable.readable;
      entry.checkbox.setAttribute("aria-label", `${this._t("selected")}: ${this._variableName(variable)}`);
      entry.row.classList.toggle("selected", entry.checkbox.checked);
      entry.name.textContent = this._variableName(variable);
      entry.metadata.textContent = this._variableIdentity(variable);
      entry.entities.textContent = this._entityInfo(variable);
      entry.entities.hidden = !entry.entities.textContent;
      const sample = this.model.latest.get(variable.wid);
      const status = !variable.readable ? "unsupported" : sample?.status || "waiting";
      entry.value.textContent = status === "ok" ? `${this._format(sample.value)} ${variable.unit || ""}` : "—";
      const stale = sample && Date.now() - Date.parse(sample.timestamp) > this.model.readingInterval(variable.wid) * 2000;
      entry.reading.textContent = status === "ok" ? `${this._time(sample.timestamp)} · ${this._age(sample.timestamp)}${stale ? " · " + this._t("stale") : ""}` : this._t(status);
      entry.reading.className = `small ${status === "read_error" || status === "invalid" ? "error" : "muted"}`;
      entry.last.textContent = sample?.status !== "ok" && Number.isFinite(sample?.last_value) ?
        `${this._t("lastKnown")}: ${this._format(sample.last_value)} ${variable.unit || ""} · ${this._time(sample.last_success)}` : "";
    }
    this.shadowRoot.querySelector(".count").textContent = `${variables.length} / ${this.model.catalog.size}`;
    this.shadowRoot.querySelector(".table-empty").hidden = variables.length > 0;
    this._pager(this.shadowRoot.querySelector(".table-pager"), this._tablePage, variables.length, 50, page => { this._tablePage = page; });
  }

  _renderCharts() {
    const selected = [...this.model.selected.keys()];
    this._chartPage = Math.min(this._chartPage, Math.max(0, Math.ceil(selected.length / 4) - 1));
    const visible = selected.slice(this._chartPage * 4, (this._chartPage + 1) * 4);
    const keep = new Set(visible);
    for (const [wid, chart] of this._charts) if (!keep.has(wid)) { chart.element.remove(); this._charts.delete(wid); }
    this._plots.querySelector(".empty")?.remove();
    if (!selected.length) this._plots.append(node("div", "empty", this._t("choose")));
    for (const wid of visible) {
      let chart = this._charts.get(wid);
      if (!chart) {
        const element = node("div", "chart"), header = node("div", "chart-head"), label = node("div", "chart-name");
        const name = node("span"), value = node("span", "number"); label.append(node("span", "swatch"), name); header.append(label, value);
        const identity = node("div", "identity small muted"), entities = node("div", "entity-info small muted");
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.setAttribute("role", "img");
        const detail = node("div", "chart-detail number"), sampleControl = node("label", "sample-control"), sampleLabel = node("span"), range = node("input");
        range.type = "range"; range.min = "0"; range.step = "1"; sampleControl.append(sampleLabel, range);
        element.append(header, identity, entities, svg, detail, sampleControl);
        chart = { element, name, value, identity, entities, svg, detail, range, sampleLabel, hover: null };
        const selectPoint = event => {
          const points = this.model.selected.get(wid)?.points || [];
          if (!points.length || !chart.xToTime) return;
          const time = chart.xToTime(event.clientX - svg.getBoundingClientRect().left);
          let index = 0;
          for (let i = 1; i < points.length; i++) if (Math.abs(Date.parse(points[i].timestamp) - time) < Math.abs(Date.parse(points[index].timestamp) - time)) index = i;
          chart.hover = points[index].timestamp;
          this._drawChart(wid, chart);
        };
        svg.onpointermove = selectPoint;
        svg.onclick = selectPoint;
        range.oninput = () => {
          const point = this.model.selected.get(wid)?.points[Number(range.value)];
          chart.hover = point?.timestamp || null;
          this._drawChart(wid, chart);
        };
        this._charts.set(wid, chart);
        this._plots.append(element);
      }
      this._drawChart(wid, chart);
    }
    this._pager(this.shadowRoot.querySelector(".chart-pager"), this._chartPage, selected.length, 4, page => { this._chartPage = page; });
  }

  _drawChart(wid, chart) {
    const variable = this.model.catalog.get(wid), points = this.model.selected.get(wid).points;
    const palette = ["var(--primary-color,#007eaa)", "var(--warning-color,#b26a00)", "var(--purple-color,#9064b9)",
      "var(--success-color,#388e3c)", "var(--error-color,#d34454)", "var(--cyan-color,#008b8b)"];
    chart.element.style.setProperty("--series", palette[Math.abs(wid) % palette.length]);
    const name = this._variableName(variable);
    chart.name.textContent = name;
    chart.identity.textContent = this._variableIdentity(variable);
    chart.entities.textContent = this._entityInfo(variable);
    chart.entities.hidden = !chart.entities.textContent;
    const latest = this.model.latest.get(wid);
    chart.value.textContent = `${this._format(latest?.status === "ok" ? latest.value : null)} ${variable.unit || ""}`;
    chart.svg.setAttribute("aria-label", `${name}: ${points.length} ${this._t("samples")}`);
    chart.sampleLabel.textContent = this._t("sample");
    chart.range.setAttribute("aria-label", `${this._t("sample")}: ${name}`);
    chart.range.disabled = !points.length;
    chart.range.max = String(Math.max(0, points.length - 1));
    const width = Math.max(200, chart.svg.clientWidth), height = 190, left = 64, right = width - 12, top = 22, bottom = 148;
    chart.svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    chart.svg.replaceChildren();
    const svgNode = (tag, attributes, text) => {
      const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const [key, value] of Object.entries(attributes)) e.setAttribute(key, value);
      if (text !== undefined) e.textContent = text;
      chart.svg.append(e);
      return e;
    };
    if (!points.length) {
      svgNode("text", { x: width / 2, y: 90, "text-anchor": "middle" }, this._t("noSamples"));
      chart.detail.textContent = this._t("noSamples");
      return;
    }
    const times = points.map(p => Date.parse(p.timestamp)), valid = points.filter(p => p.status === "ok");
    const values = valid.map(p => p.value), low = values.length ? Math.min(...values) : 0, high = values.length ? Math.max(...values) : 1;
    const pad = high === low ? Math.abs(high) * .05 || 1 : Math.max((high - low) * .15, Math.abs(high) * .01);
    const min = low - pad, max = high + pad;
    const first = Math.min(...times), last = Math.max(...times), span = Math.max(1000, last - first);
    const start = last === first ? first - 500 : first;
    const x = time => left + (right - left) * (time - start) / span;
    const y = value => bottom - (bottom - top) * (value - min) / (max - min);
    chart.xToTime = pixel => start + (pixel - left) / (right - left) * span;
    const labels = this._axisLabels(min, max);
    for (let i = 0; i < 3; i++) {
      const yy = top + (bottom - top) * i / 2;
      svgNode("line", { x1: left, x2: right, y1: yy, y2: yy, stroke: "var(--divider-color,#dce4eb)" });
      svgNode("text", { x: left - 6, y: yy + 4, "text-anchor": "end" }, labels[i]);
    }
    svgNode("text", { x: left, y: 13 }, variable.unit || this._t("measurement"));
    const ticks = first === last ? [first] : width < 290 ? [first, last] : [first, (first + last) / 2, last];
    ticks.forEach((time, index) => svgNode("text", { x: x(time), y: 175,
      "text-anchor": ticks.length === 1 ? "middle" : index === 0 ? "start" : index === ticks.length - 1 ? "end" : "middle" }, this._time(new Date(time).toISOString())));
    let path = "", previous, runLength = 0, lastInRun;
    const isolated = [];
    const finishRun = () => { if (runLength === 1) isolated.push(lastInRun); runLength = 0; };
    points.forEach((point, index) => {
      if (point.status !== "ok") { finishRun(); previous = null; return; }
      const xx = x(times[index]), yy = y(point.value);
      if (!previous || point.breakBefore) { finishRun(); path += `M${xx},${yy} `; }
      else path += variable.type === "Float" ? `L${xx},${yy} ` : `H${xx} V${yy} `;
      runLength++;
      lastInRun = point;
      previous = point;
    });
    finishRun();
    svgNode("path", { d: path, fill: "none", stroke: "var(--series)", "stroke-width": 2, "stroke-linejoin": "round" });
    for (const point of isolated) svgNode("circle", { cx: x(Date.parse(point.timestamp)), cy: y(point.value), r: 3, fill: "var(--series)" });
    let index = chart.hover ? points.findIndex(p => p.timestamp === chart.hover) : points.length - 1;
    if (index < 0) { index = points.length - 1; chart.hover = null; }
    const point = points[index];
    chart.range.value = String(index);
    chart.range.setAttribute("aria-valuetext", `${this._time(point.timestamp)}: ${point.status === "ok" ? this._format(point.value) : this._t(point.status)}`);
    chart.detail.textContent = `${this._time(point.timestamp)} · ${point.status === "ok" ? this._format(point.value) + " " + (variable.unit || "") : this._t(point.status)} · ${points.length} ${this._t("samples")}`;
    if (chart.hover) {
      const xx = x(Date.parse(point.timestamp));
      svgNode("line", { x1: xx, x2: xx, y1: top, y2: bottom, stroke: "var(--secondary-text-color,#526775)", "stroke-width": 1 });
      if (point.status === "ok") svgNode("circle", { cx: xx, cy: y(point.value), r: 4, fill: "var(--series)" });
    }
  }
}

if (!customElements.get("amit-monitor-panel")) customElements.define("amit-monitor-panel", AMiTMonitorPanel);
