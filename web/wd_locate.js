// wd_locate.js — pure resolution of a (possibly compound) node id into
// an actual node object, walking into nested subgraph interiors as
// needed. No DOM/canvas/litegraph globals touched here — this only
// needs plain objects shaped like { _nodes/nodes: [...], getNodeById }
// and node objects shaped like { id, subgraph? }, so it's unit-tested
// directly in Node with mocks, same discipline as wd_render.js.
//
// Compound ids come from ComfyUI's backend flattening a node inside a
// subgraph instance into "<outerInstanceId>:<innerNodeId>" (and deeper
// for nested subgraphs: "82:81:5"). litegraph's own getNodeById only
// ever knows about plain ids in whatever graph context is currently
// active, so resolving a compound id means walking one segment at a
// time, descending into node.subgraph between segments.

export function splitCompoundId(raw) {
  return String(raw)
    .split(":")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function findNodeInGraph(graph, idStr) {
  if (!graph) return null;
  if (typeof graph.getNodeById === "function") {
    const byNum = graph.getNodeById(Number(idStr));
    if (byNum) return byNum;
    const byStr = graph.getNodeById(idStr);
    if (byStr) return byStr;
  }
  const nodes = graph._nodes || graph.nodes;
  if (Array.isArray(nodes)) {
    return nodes.find((n) => String(n.id) === String(idStr)) || null;
  }
  return null;
}

/**
 * Checks whether the immediate containing subgraph instance already
 * has a widget with this name — i.e. the parameter is promoted/exposed
 * onto the outer node, so it can be changed right there without ever
 * entering the subgraph. Deliberately name-based rather than checking
 * for any internal "promoted widget" class: ComfyUI's promotion
 * internals have shifted across versions (and have open bugs around
 * nested promotion), so matching by widget name is the version-stable
 * signal — it answers "can the user click this on the outer node"
 * regardless of what ComfyUI calls the mechanism internally.
 *
 * Only checks the immediate parent (the last entry in openChain), not
 * every ancestor level — ComfyUI's own promotion is documented as
 * reliable one level up and flaky beyond that, so a deeper search
 * would mostly be guessing past where the real feature itself holds up.
 *
 * Returns the outer node if a same-named widget exists there, else null.
 */
export function findPromotedHost(openChain, widgetKey) {
  if (!widgetKey || !openChain || openChain.length === 0) return null;
  const immediateParent = openChain[openChain.length - 1].outerNode;
  const hasMatch = (immediateParent.widgets || []).some((w) => w.name === widgetKey);
  return hasMatch ? immediateParent : null;
}
/**
 * Walk idChain (e.g. ["82","81"]) starting at rootGraph, descending
 * into .subgraph between segments.
 *
 * Returns:
 *   { found:true,  finalNode, openChain:[{outerNode,subgraph}, ...] }
 *   { found:false, failedAt:<index>, failedId:<segment>, reason:"not-found"|"no-subgraph" }
 *
 * openChain lists, outermost first, every subgraph interior that must
 * be entered (via canvas.openSubgraph) before finalNode is visible.
 * For a plain id with no ":" it's an empty array.
 */
export function resolveCompoundNode(rootGraph, idChain) {
  let graph = rootGraph;
  const openChain = [];
  let node = null;

  for (let i = 0; i < idChain.length; i++) {
    const wantId = idChain[i];
    node = findNodeInGraph(graph, wantId);

    if (!node) {
      return { found: false, finalNode: null, openChain, failedAt: i, failedId: wantId, reason: "not-found" };
    }

    const isLastSegment = i === idChain.length - 1;
    if (!isLastSegment) {
      if (!node.subgraph) {
        return {
          found: false,
          finalNode: null,
          openChain,
          failedAt: i,
          failedId: wantId,
          reason: "no-subgraph",
        };
      }
      openChain.push({ outerNode: node, subgraph: node.subgraph });
      graph = node.subgraph;
    }
  }

  return { found: true, finalNode: node, openChain, failedAt: null, failedId: null, reason: null };
}
