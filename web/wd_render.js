// wd_render.js — pure diff -> HTML string renderer.
//
// No DOM, no imports, no side effects: takes the object that
// diff.py's diff_graphs() returns and produces an HTML string. Kept
// separate so it can be unit-tested in Node (tests/test_render.mjs)
// exactly like the Python pipeline is. ComfyUI will also fetch this
// as a standalone extension file, which is harmless since it only
// exports.
//
// Consumed shape:
//   { added_nodes:[{id,class_type,title}],
//     removed_nodes:[...],
//     type_swapped:[{id,old_type,new_type,title}],
//     changed:[{id,class_type,title,widgets:{k:[old,new]},links:{k:{old,new}}}],
//     unchanged_count:int }

export function esc(v) {
  return String(v).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

export function fmt(v) {
  if (v === null || v === undefined) return "∅";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "boolean") return v ? "true" : "false";
  return esc(v);
}

function sChip(color, n, label) {
  return `<div class="wd-s"><span class="wd-k" style="background:${color}"></span><b>${n}</b> ${label}</div>`;
}

// A clickable node-id badge ("#27 ⌖"). The host (wedge_diff.js) wires
// any .wd-noderef element to locate+flash that node on the canvas.
function idBadge(id, type) {
  return `<span class="wd-cid wd-noderef" data-node-id="${esc(id)}" data-type="${esc(
    type || ""
  )}" title="Locate on canvas">#${esc(id)} ⌖</span>`;
}

// A readable, clickable endpoint chip for a link rewire. `labels` is
// the labels_a or labels_b map; falls back to "#id" if unknown, and to
// "∅" when the endpoint is null (input newly connected / disconnected).
function endpointChip(labels, id) {
  if (id === undefined || id === null) {
    return `<span class="wd-noderef-none">∅</span>`;
  }
  const e = (labels && labels[id]) || {};
  const name = e.title || e.type || `#${id}`;
  return `<span class="wd-noderef wd-endpoint" data-node-id="${esc(id)}" data-type="${esc(
    e.type || ""
  )}" title="Locate on canvas"><span class="wd-ep-name">${esc(
    name
  )}</span> <span class="wd-noderef-id">#${esc(id)}</span></span>`;
}

// A clickable parameter row for a widget value change. Clicking jumps
// to the node AND highlights this specific widget's row on canvas
// (not just the node border) — see flashNodeGold's widgetKey param.
function widgetRow(nodeId, nodeType, key, o, nv) {
  return `<div class="wd-kv wd-noderef wd-widgetrow" data-node-id="${esc(
    nodeId
  )}" data-type="${esc(nodeType || "")}" data-widget="${esc(
    key
  )}" title="Locate this parameter on canvas"><span class="wd-key">${esc(
    key
  )}</span><span class="wd-val"><span class="wd-old">${fmt(
    o
  )}</span><span class="wd-ar">→</span><span class="wd-new">${fmt(nv)}</span></span></div>`;
}

function group(title, color, n, inner) {
  return `<div class="wd-group"><div class="wd-gh"><span class="wd-n" style="background:${color}">${n}</span>${title}</div>${inner}</div>`;
}

export function renderDiff(d) {
  if (!d || typeof d !== "object") {
    return `<div class="wd-empty">No diff data.</div>`;
  }
  const added = d.added_nodes || [];
  const removed = d.removed_nodes || [];
  const swapped = d.type_swapped || [];
  const changed = d.changed || [];
  const unchanged = d.unchanged_count || 0;
  const labelsA = d.labels_a || {};
  const labelsB = d.labels_b || {};

  const nothing =
    !added.length && !removed.length && !swapped.length && !changed.length;
  if (nothing) {
    return `<div class="wd-identical">
      <div class="wd-identical-mark">≡</div>
      <div>These two runs are identical.</div>
      <div class="wd-sub2">${unchanged} nodes, no differences</div>
    </div>`;
  }

  let h = "";

  // summary strip
  h += '<div class="wd-summary">';
  h += sChip("var(--wd-add)", added.length, "added");
  h += sChip("var(--wd-del)", removed.length, "removed");
  h += sChip("var(--wd-swap)", swapped.length, "swapped");
  h += sChip("var(--wd-gold)", changed.length, "changed");
  h += "</div>";

  // type swaps first — easiest to miss when scanning
  if (swapped.length) {
    h += group(
      "Type swapped",
      "var(--wd-swap)",
      swapped.length,
      swapped
        .map(
          (n) => `
      <div class="wd-card wd-swapc wd-has-body">
        <div class="wd-ch"><span class="wd-sigil">⇄</span><span class="wd-ctype">${esc(
            n.title || n.new_type
          )}</span>${idBadge(n.id, n.new_type)}</div>
        <div class="wd-body"><div class="wd-swap-line"><span class="wd-old">${esc(
            n.old_type
          )}</span><span class="wd-ar">→</span><span class="wd-new">${esc(
            n.new_type
          )}</span></div></div>
      </div>`
        )
        .join("")
    );
  }

  // changed widgets + links — the hero case
  if (changed.length) {
    h += group(
      "Parameters changed",
      "var(--wd-gold)",
      changed.length,
      changed
        .map((n) => {
          let body = "";
          for (const [k, pair] of Object.entries(n.widgets || {})) {
            const o = Array.isArray(pair) ? pair[0] : undefined;
            const nv = Array.isArray(pair) ? pair[1] : undefined;
            body += widgetRow(n.id, n.class_type, k, o, nv);
          }
          for (const [k, lk] of Object.entries(n.links || {})) {
            const from = endpointChip(labelsA, lk.old ? lk.old[0] : undefined);
            const to = endpointChip(labelsB, lk.new ? lk.new[0] : undefined);
            body += `<div class="wd-link-line"><span class="wd-link-in">${esc(
              k
            )}</span> input: ${from} <span class="wd-ar">→</span> ${to}</div>`;
          }
          const has = body ? "wd-has-body" : "";
          return `<div class="wd-card ${has}">
        <div class="wd-ch"><span class="wd-sigil" style="color:var(--wd-gold)">~</span><span class="wd-ctype">${esc(
            n.title || n.class_type
          )}</span>${idBadge(n.id, n.class_type)}</div>
        ${body ? `<div class="wd-body">${body}</div>` : ""}
      </div>`;
        })
        .join("")
    );
  }

  // added
  if (added.length) {
    h += group(
      "Added",
      "var(--wd-add)",
      added.length,
      added
        .map(
          (n) => `
      <div class="wd-card wd-addc"><div class="wd-ch"><span class="wd-sigil">+</span><span class="wd-ctype">${esc(
            n.title || n.class_type
          )}</span>${idBadge(n.id, n.class_type)}</div></div>`
        )
        .join("")
    );
  }

  // removed
  if (removed.length) {
    h += group(
      "Removed",
      "var(--wd-del)",
      removed.length,
      removed
        .map(
          (n) => `
      <div class="wd-card wd-delc"><div class="wd-ch"><span class="wd-sigil">−</span><span class="wd-ctype">${esc(
            n.title || n.class_type
          )}</span><span class="wd-cid">#${esc(n.id)}</span></div></div>`
        )
        .join("")
    );
  }

  // unchanged — static count (diff_graphs returns only the number)
  h += `<div class="wd-unchanged">${unchanged} nodes unchanged</div>`;

  return h;
}
