// test_render.mjs — Node unit test for wd_render.js
import { renderDiff, esc, fmt } from "../web/wd_render.js";

let pass = 0,
  fail = 0;
function ok(cond, label) {
  if (cond) pass++;
  else {
    fail++;
    console.log("FAIL:", label);
  }
}

// fmt / esc
ok(fmt(7) === "7", "fmt int");
ok(fmt(7.5) === "7.50", "fmt float 2dp");
ok(fmt(null) === "∅", "fmt null");
ok(fmt(true) === "true", "fmt bool");
ok(esc("<script>") === "&lt;script&gt;", "esc tags");
ok(esc('a"b') === "a&quot;b", "esc quote");

// full diff
const DIFF = {
  added_nodes: [{ id: "27", class_type: "FilmGrain", title: "Film Grain" }],
  removed_nodes: [{ id: "5", class_type: "VAEDecode", title: "VAE Decode" }],
  type_swapped: [
    {
      id: "4",
      old_type: "WanVideoModelLoader",
      new_type: "WanVideoModelLoaderGGUF",
      title: "Load WAN Model",
    },
  ],
  changed: [
    {
      id: "3",
      class_type: "KSampler",
      title: "KSampler",
      widgets: { cfg: [6.0, 7.5], steps: [20, 25] },
      links: {},
    },
    {
      id: "9",
      class_type: "SaveImage",
      title: "Save Image",
      widgets: {},
      links: { images: { old: ["8", 0], new: ["27", 0] } },
    },
  ],
  unchanged_count: 14,
  labels_a: {
    "8": { type: "ColorMatch", title: "Color Match" },
    "1": { type: "CheckpointLoaderSimple", title: "Load Checkpoint" },
  },
  labels_b: {
    "27": { type: "FilmGrain", title: "Film Grain" },
    "1": { type: "CheckpointLoaderSimple", title: "Load Checkpoint" },
  },
};

const html = renderDiff(DIFF);
ok(html.includes("Film Grain"), "added node shown");
ok(html.includes("VAE Decode"), "removed node shown");
ok(html.includes("WanVideoModelLoaderGGUF"), "type swap new type shown");
ok(html.includes("⇄"), "type swap sigil");
ok(html.includes("6") && html.includes("7.50"), "widget old+new shown");
ok(html.includes("→"), "arrow present");
ok(html.includes("Color Match") && html.includes("Film Grain"), "link endpoints show readable names");
ok(html.includes('data-node-id="8"') && html.includes('data-node-id="27"'), "endpoints are clickable noderefs");
ok(html.includes("wd-noderef"), "noderef class present for locate wiring");
ok(html.includes("wd-widgetrow"), "widget rows are clickable noderefs");
ok(html.includes('data-widget="cfg"'), "widget row carries its key for targeted highlight");
ok(html.includes('data-widget="steps"'), "second widget row carries its own key");
ok(html.includes("14 nodes unchanged"), "unchanged count shown");
ok(html.includes("wd-card"), "namespaced class used");
ok(!html.includes('class="card"'), "no un-namespaced .card leak");

// identical
const same = renderDiff({
  added_nodes: [],
  removed_nodes: [],
  type_swapped: [],
  changed: [],
  unchanged_count: 12,
});
ok(same.includes("identical"), "identical case handled");
ok(same.includes("12 nodes"), "identical shows count");

// garbage
ok(renderDiff(null).includes("No diff"), "null diff handled");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
