// Run with: node --test tests/test_monitor_frontend.mjs
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// History has no DOM dependency. Only the panel's base class and registration
// need substitutes to import the same module used by the browser.
globalThis.HTMLElement = class {};
globalThis.customElements = { get: () => true };
const source = await readFile(new URL("../custom_components/amit/frontend/monitor.js", import.meta.url), "utf8");
const { MonitorHistory, TRANSLATIONS, AMiTMonitorPanel } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

const variable = (wid = 1, revision = 1, readable = true) => ({ wid, revision, readable, type: "Float", name: `Value ${wid}` });
const reading = (sequence, wid = 1, value = sequence, revision = 1) => ({
  wid, revision, sequence, value, status: "ok", timestamp: new Date(1_700_000_000_000 + sequence * 1000).toISOString(),
});
const snapshot = (variables = [variable()], sequence = 0, samples = [], runtime = "first") => ({
  kind: "snapshot", runtime_id: runtime, variables, sequence, samples, scan_interval: 30,
});
const send = (model, sample, runtime = "first") => model.sample({ runtime_id: runtime, sample });

test("snapshot values never become recorded history", () => {
  const model = new MonitorHistory();
  model.snapshot(snapshot(undefined, 5, [reading(5)]));
  model.select(1, true);
  assert.equal(model.latest.get(1).value, 5);
  assert.equal(model.count, 0);
  assert.equal(send(model, reading(5)), false);
  send(model, reading(6, 1, 5));
  assert.equal(model.count, 1);
  assert.equal(model.selected.get(1).points[0].value, 5);
});

test("unchanged values are new readings; duplicate sequences are ignored", () => {
  const model = new MonitorHistory();
  model.snapshot(snapshot()); model.select(1, true);
  send(model, reading(1, 1, 7)); send(model, reading(2, 1, 7)); send(model, reading(2, 1, 7));
  assert.deepEqual(model.selected.get(1).points.map(p => p.sequence), [1, 2]);
});

test("deselect and reselect begin a new series", () => {
  const model = new MonitorHistory(); model.snapshot(snapshot()); model.select(1, true);
  send(model, reading(1)); model.select(1, false); model.select(1, true);
  assert.equal(model.count, 0); assert.equal(model.selected.get(1).points.length, 0);
  send(model, reading(2)); assert.equal(model.count, 1);
});

test("clear history keeps selection and latest values but rejects old samples", () => {
  const model = new MonitorHistory(); model.snapshot(snapshot()); model.select(1, true);
  send(model, reading(1)); model.clearHistory(); send(model, reading(1));
  assert.equal(model.count, 0); assert.equal(model.latest.get(1).value, 1);
  assert.equal(model.selected.size, 1); send(model, reading(2)); assert.equal(model.count, 1);
});

test("resume snapshot skips missed readings and inserts a discontinuity", () => {
  const model = new MonitorHistory(); model.snapshot(snapshot()); model.select(1, true);
  send(model, reading(1)); model.breakSeries(); model.snapshot(snapshot(undefined, 5, [reading(5)]));
  assert.equal(model.count, 1); assert.equal(model.latest.get(1).value, 5);
  send(model, reading(5)); send(model, reading(6));
  assert.deepEqual(model.selected.get(1).points.map(p => [p.sequence, p.breakBefore]), [[1, false], [6, true]]);
});

test("failure samples form gaps and nonfinite samples are normalized", () => {
  const model = new MonitorHistory(); model.snapshot(snapshot()); model.select(1, true);
  send(model, reading(1));
  send(model, { ...reading(2), status: "read_error", value: null });
  send(model, reading(3, 1, Infinity));
  assert.equal(model.selected.get(1).points[1].status, "read_error");
  assert.equal(model.selected.get(1).points[2].status, "invalid");
  assert.equal(model.selected.get(1).points[2].value, null);
});

test("catalog changes preserve unchanged series and discard changed definitions", () => {
  const model = new MonitorHistory(); model.snapshot(snapshot([variable(1), variable(2)]));
  model.select(1, true); model.select(2, true); send(model, reading(1)); send(model, reading(2, 2));
  model.snapshot(snapshot([variable(1), variable(2, 2)], 2));
  assert.equal(model.selected.get(1).points.length, 1);
  assert.equal(model.selected.get(2).points.length, 0);
  assert.equal(model.latest.has(2), false);
  assert.equal(send(model, reading(3, 2, 9, 1)), false);
  send(model, reading(4, 2, 9, 2)); assert.equal(model.count, 2);
  model.snapshot(snapshot([variable(1, 1, false)], 4));
  assert.equal(model.selected.size, 0); assert.equal(model.count, 0);
});

test("PLC runtime changes clear old points and accept the restarted sequence", () => {
  const model = new MonitorHistory(); model.snapshot(snapshot()); model.select(1, true);
  send(model, reading(100)); model.snapshot(snapshot(undefined, 1, [], "second"));
  assert.equal(model.count, 0); assert.equal(model.latest.size, 0);
  assert.equal(send(model, reading(101), "first"), false);
  send(model, reading(2), "second"); assert.equal(model.count, 1);
});

test("per-variable and global limits evict the oldest samples", () => {
  const model = new MonitorHistory(3, 4); model.snapshot(snapshot([variable(1), variable(2)]));
  model.select(1, true); model.select(2, true);
  for (let i = 1; i <= 5; i++) send(model, reading(i));
  assert.deepEqual(model.selected.get(1).points.map(p => p.sequence), [3, 4, 5]);
  send(model, reading(6, 2)); send(model, reading(7, 2));
  assert.deepEqual(model.selected.get(1).points.map(p => p.sequence), [4, 5]);
  assert.equal(model.count, 4); assert.equal(model.trimmed, true);
  model.select(2, false); assert.equal(model.count, 2);
});

test("default limits remain bounded over a long session", () => {
  const model = new MonitorHistory(); const variables = Array.from({ length: 30 }, (_, i) => variable(i));
  model.snapshot(snapshot(variables)); variables.forEach(v => model.select(v.wid, true));
  for (let i = 1; i <= 61000; i++) send(model, reading(i, i % 30));
  assert.equal(model.count, 50000);
  assert.equal([...model.selected.values()].reduce((sum, s) => sum + s.points.length, 0), 50000);
  assert.ok([...model.selected.values()].every(s => s.points.length <= 2000));
});

test("malformed, obsolete and unknown samples cannot enter history", () => {
  const model = new MonitorHistory(); model.snapshot(snapshot()); model.select(1, true);
  for (const sample of [reading(1, 99), reading(1, 1, 1, 99), { ...reading(1), timestamp: "invalid" }, { ...reading(1), sequence: 1.1 }]) {
    assert.equal(send(model, sample), false);
  }
  assert.equal(model.count, 0);
});

test("Czech and English translations contain the same nonempty keys", () => {
  assert.deepEqual(Object.keys(TRANSLATIONS.cs).sort(), Object.keys(TRANSLATIONS.en).sort());
  for (const messages of Object.values(TRANSLATIONS)) assert.ok(Object.values(messages).every(v => typeof v === "string" && v.length));
});

test("entity updates change labels without touching samples, gaps, sequence, or PLC definitions", () => {
  const model = new MonitorHistory(); model.snapshot(snapshot()); model.select(1, true);
  send(model, reading(1));
  const series = model.selected.get(1), points = series.points, latest = model.latest.get(1);
  const entities = [{ entity_id: "sensor.renamed", name: "Living room", custom_name: "Living room", disabled: true }];
  model.entityMetadata({ runtime_id: "first", sequence: 999, variables: [
    { wid: 1, configured: true, entities, name: "Wrong PLC name", revision: 99, readable: false },
  ] });
  assert.deepEqual(model.catalog.get(1), { ...variable(), configured: true, entities });
  assert.equal(model.selected.get(1), series); assert.equal(series.points, points);
  assert.equal(model.latest.get(1), latest); assert.equal(model.sequence, 1);
  assert.equal(series.gap, false); assert.equal(series.floor, 1); assert.equal(model.count, 1);
  send(model, reading(2));
  assert.deepEqual(points.map(p => p.breakBefore), [false, false]);
  model.breakSeries();
  model.entityMetadata({ runtime_id: "first", variables: [{ wid: 1, configured: false, entities: [] }] });
  assert.equal(series.gap, true); assert.equal(model.count, 2);
  assert.deepEqual(model.catalog.get(1).entities, []);
});

test("metadata from another PLC runtime and malformed or unknown patches are ignored", () => {
  const model = new MonitorHistory(); model.snapshot(snapshot());
  const before = model.catalog.get(1);
  for (const event of [
    { runtime_id: "other", variables: [{ wid: 1, configured: true, entities: [] }] },
    { runtime_id: "first", variables: null },
    { runtime_id: "first", variables: [null, { wid: 1 }, { wid: 1, configured: true, entities: null },
      { wid: 99, configured: true, entities: [] }] },
  ]) model.entityMetadata(event);
  assert.equal(model.catalog.get(1), before); assert.equal(model.catalog.size, 1);
});

test("snapshot metadata supports multiple entities, disabled entries, and older API snapshots", () => {
  const model = new MonitorHistory();
  const entities = [{ entity_id: "sensor.one", name: "First", custom_name: "First", disabled: false },
    { entity_id: "number.two", name: "Second", custom_name: null, disabled: true }];
  model.snapshot(snapshot([{ ...variable(), configured: true, entities }]));
  assert.deepEqual(model.catalog.get(1).entities, entities);
  entities[0].name = "Caller change";
  assert.equal(model.catalog.get(1).entities[0].name, "First");
  model.snapshot(snapshot());
  assert.deepEqual(model.catalog.get(1), { ...variable(), configured: false, entities: [] });
});

test("axis precision distinguishes small, negative, and narrowly spaced ticks", () => {
  const ranges = [[.048505, .049995], [-.049995, -.048505], [-.0001, .0001],
    [1e6, 1e6 + 1], [1e-38, 1.1e-38], [-3.4e38, -3e38], [0, 1]];
  for (const language of ["cs", "en"]) {
    for (const [min, max] of ranges) {
      const labels = AMiTMonitorPanel.prototype._axisLabels.call({ _lang: language }, min, max);
      assert.equal(labels.length, 3);
      assert.equal(new Set(labels).size, 3, `${language} scale ${min} to ${max}: ${labels}`);
    }
    const labels = AMiTMonitorPanel.prototype._axisLabels.call({ _lang: language }, .048505, .049995);
    assert.ok(labels.some(label => label.includes(language === "cs" ? "0,049" : "0.049")));
  }
});

test("adaptive axis labels do not change displayed reading precision", () => {
  const format = value => AMiTMonitorPanel.prototype._format.call({ _lang: "en" }, value);
  assert.equal(format(.0495), "0.0495");
  assert.equal(format(2147483647), "2,147,483,647");
  assert.equal(format(-2147483648), "-2,147,483,648");
});
