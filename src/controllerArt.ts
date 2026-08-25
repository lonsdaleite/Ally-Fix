/**
 * Controller picture in Steam's controller settings.
 *
 * The diagram there is a CSS background chosen by the controller *type* class on an
 * ancestor (`controller_rog_ally`, `controller_steamos_handheld`, …). The stock sheet has
 * no rule for the Ally, so the base rule wins and draws the original Steam Controller with
 * two trackpads. Steam does own a handheld outline — the `LegionGoS` SVG component it
 * uses on the game-launch interstitial for every third-party handheld — so that component
 * is rendered to an SVG string at runtime and set as the background through a `<style>`
 * in every window document. Nothing is shipped: the art stays inside the client.
 *
 * Anchors: the export name `LegionGoS`, and the file name of the base rule's image
 * (`cropped_controller_config_controller.png`) to learn the hashed diagram class. Either
 * missing → stock picture, reported as a detail.
 */

const STYLE_ID = "ally-fix-art";
const BASE_IMAGE = "cropped_controller_config_controller.png";
const TYPE_CLASSES = ["controller_rog_ally", "controller_steamos_handheld"];
const RETRY_MS = [500, 1000, 2000, 4000, 8000]; // a new window's sheets load after the popup is created

declare global {
  interface Window {
    g_PopupManager?: any;
    __allyFixArtCss?: string | null;
    __allyFixArtHooked?: boolean;
  }
}

// ---- rendering Steam's own component to markup ----------------------------------------
const KEEP_CASE = new Set([
  "viewBox", "preserveAspectRatio", "gradientUnits", "gradientTransform", "patternUnits", "patternContentUnits",
  "markerWidth", "markerHeight", "refX", "refY", "spreadMethod", "startOffset", "textLength", "lengthAdjust",
  "clipPathUnits", "maskUnits", "maskContentUnits", "primitiveUnits", "baseFrequency", "numOctaves", "stdDeviation", "xmlns",
]);
const SELF_CLOSING = new Set(["path", "circle", "rect", "ellipse", "line", "polyline", "polygon", "stop", "use", "image"]);
const kebab = (k: string) => (KEEP_CASE.has(k) ? k : k.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase());
const esc = (s: unknown) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function renderElement(node: any, depth: number): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return esc(node);
  if (Array.isArray(node)) return node.map((n) => renderElement(n, depth)).join("");
  if (depth > 60) return "";
  const type = node.type;
  const props = node.props ?? {};
  if (typeof type === "function") {
    try { return renderElement(type(props), depth + 1); } catch { return ""; }
  }
  if (typeof type === "object" && type !== null) { // memo / forwardRef / fragment
    const inner = type.render ?? type.type;
    if (typeof inner === "function") {
      try { return renderElement(inner(props), depth + 1); } catch { return ""; }
    }
    return renderElement(props.children, depth + 1);
  }
  if (typeof type !== "string") return renderElement(props.children, depth + 1);
  const attrs: string[] = [];
  for (const [k, v] of Object.entries(props)) {
    if (k === "children" || k === "key" || k === "ref") continue;
    if (v == null || typeof v === "function" || typeof v === "boolean" || typeof v === "object") continue;
    attrs.push(`${kebab(k === "className" ? "class" : k)}="${esc(v)}"`);
  }
  const inner = renderElement(props.children, depth + 1);
  const a = attrs.length ? " " + attrs.join(" ") : "";
  return !inner && SELF_CLOSING.has(type) ? `<${type}${a}/>` : `<${type}${a}>${inner}</${type}>`;
}

function findComponent(req: any): ((props: any) => any) | null {
  for (const id of Object.keys(req.m)) {
    let src = "";
    try { src = String(req.m[id]); } catch { continue; }
    if (!src.includes("LegionGoS")) continue;
    let exp: any;
    try { exp = req(id); } catch { continue; }
    if (!exp || typeof exp !== "object") continue;
    let v: any;
    try { v = exp.LegionGoS; } catch { continue; }
    if (typeof v === "function") return v;
  }
  return null;
}

/** CSS that swaps the diagram, or an error string. */
function buildCss(req: any): { css?: string; error?: string } {
  const comp = findComponent(req);
  if (!comp) return { error: "LegionGoS component not found" };
  let svg = "";
  try { svg = renderElement(comp({}), 0); } catch (e) { return { error: `render failed: ${e}` }; }
  if (!svg.startsWith("<svg")) return { error: "component did not render to <svg>" };
  const uri = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(svg)));
  return { css: uri };
}

// ---- windows ------------------------------------------------------------------------------
function diagramClass(doc: Document): string | null {
  for (const ss of Array.from(doc.styleSheets)) {
    let rules: CSSRuleList;
    try { rules = ss.cssRules; } catch { continue; }
    for (const r of Array.from(rules)) {
      const sr = r as CSSStyleRule;
      if (sr.cssText?.includes(BASE_IMAGE) && sr.selectorText && !sr.selectorText.includes(" ")) return sr.selectorText;
    }
  }
  return null;
}

function applyToDocument(doc: Document, uri: string): boolean {
  const cls = diagramClass(doc);
  if (!cls || !doc.head) return false;
  let st = doc.getElementById(STYLE_ID) as HTMLStyleElement | null;
  if (!st) {
    st = doc.createElement("style");
    st.id = STYLE_ID;
    doc.head.appendChild(st);
  }
  st.textContent = `${TYPE_CLASSES.map((t) => `.${t} ${cls}`).join(", ")} { background-image: url("${uri}"); }`;
  return true;
}

function removeFromDocument(doc: Document) {
  doc.getElementById(STYLE_ID)?.remove();
}

function documents(): Document[] {
  const out: Document[] = [];
  const pm = window.g_PopupManager;
  if (!pm?.m_mapPopups) return out;
  for (const v of pm.m_mapPopups.values()) {
    const doc = v?.m_popup?.document;
    if (doc) out.push(doc);
  }
  return out;
}

/** A window created later (desktop mode opens settings in its own): apply once its sheets are in. */
function applyWhenReady(popup: any, attempt = 0) {
  const uri = window.__allyFixArtCss;
  if (!uri) return;
  const doc = popup?.m_popup?.document;
  if (doc && applyToDocument(doc, uri)) return;
  if (attempt < RETRY_MS.length) window.setTimeout(() => applyWhenReady(popup, attempt + 1), RETRY_MS[attempt]);
}

function hookPopups() {
  if (window.__allyFixArtHooked) return;
  const pm = window.g_PopupManager;
  if (typeof pm?.AddPopupCreatedCallback !== "function") return;
  pm.AddPopupCreatedCallback((popup: any) => applyWhenReady(popup));
  window.__allyFixArtHooked = true;
}

/** Returns "ok" or the reason the stock picture stays. */
export function applyControllerArt(req: any): string {
  const built = buildCss(req);
  if (!built.css) return built.error ?? "unknown";
  window.__allyFixArtCss = built.css;
  hookPopups();
  let n = 0;
  for (const doc of documents()) if (applyToDocument(doc, built.css)) n++;
  return n > 0 ? "ok" : "diagram rule not found in any window";
}

export function revertControllerArt(): void {
  window.__allyFixArtCss = null;
  for (const doc of documents()) removeFromDocument(doc);
}
