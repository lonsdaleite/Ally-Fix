/**
 * UI half of the Gamepad Layout Fix: take the lower rear pair (L5/R5) out of Steam Input.
 *
 * The native shim clears the TRACKPAD and CAPJOYSTICK capability bits; it cannot express
 * "upper rear pair only", because Steam models the upper pair as an extension of the lower
 * one (its caps_filter is GRIPS|UPPERGRIPS) and gates the whole rear-button section on the
 * lower-left entry. So the metadata table is edited instead, anchored on the entries'
 * string ids (the same ids configs use), never on offsets in the bundle:
 *   - both *_Upper entries and LeftGrip get caps_filter = UPPERGRIPS (LeftGrip keeps the
 *     section gate open), LeftGrip gets source_filter = -1 (hidden in every source),
 *   - then the GRIPS bit is cleared on the controller objects, which drops RightGrip by
 *     Steam's own rule and removes the pair from the diagram and the binding pickers.
 * The bit lives on objects Steam rebuilds on native events (game launch…), so the clamp is
 * a lazy read-wrap of the controller store's getters, not a one-shot write.
 *
 * Order matters: the table edits are all-or-nothing and self-checked first; the bit is
 * only clamped once they hold. Any failure leaves the client stock (four rear buttons).
 */
import { reportGamepadLayoutUi } from "./api";
import { store } from "./store";
import type { GamepadLayoutDetails, UiPatchResult } from "./types";

// Product ids InputPlumber's deck-uhid target presents on this device: the Ally's own, and
// the generic SteamOS-handheld one the Gyro Fix's Deck Emulation mode switches to. Steam
// applies the same capability constant to both; a real Steam Controller (which does have
// grips) never carries either id.
const PIDS = [0x12fd, 0x12f0];
const GRIPS = 1n << 10n;
const UPPERGRIPS = 1n << 22n;
const STOCK_CAPS = 0x160bfffn;
const HIDE_IN_ALL_SOURCES = -1;
const IDS = ["LeftGrip", "RightGrip", "LeftGrip_Upper", "RightGrip_Upper"] as const;
const GETTERS = ["GetController", "GetControllers", "GetControllersSorted", "GetUnboundControllers"];

type GripId = (typeof IDS)[number];
type Entry = { id: string; caps_filter: number | bigint; source_filter?: number };
type Saved = { caps_filter: number | bigint; source_filter: number | null };

interface Patched {
  byId: Record<GripId, Entry>;
  orig: Record<GripId, Saved>;
  store: any;
  wrapped: Record<string, (...args: any[]) => any>;
  result: UiPatchResult;
}

declare global {
  interface Window {
    __allyFixLayout?: Patched;
  }
}

let req: any;
function webpackRequire(): any {
  if (!req) (window as any).webpackChunksteamui?.push([[Math.random()], {}, (r: any) => { req = r; }]);
  return req;
}

/** Walk the module factories whose source mentions `needle`, evaluate them, hand each export to `pick`. */
function findExport(r: any, needle: string, pick: (value: any) => boolean): { value: any; moduleId: string } | null {
  for (const id of Object.keys(r.m)) {
    let src = "";
    try { src = String(r.m[id]); } catch { continue; }
    if (!src.includes(needle)) continue;
    let exp: any;
    try { exp = r(id); } catch { continue; }
    if (!exp || typeof exp !== "object") continue;
    for (const k of Object.keys(exp)) {
      let v: any;
      try { v = exp[k]; } catch { continue; }
      if (v && typeof v === "object" && pick(v)) return { value: v, moduleId: id };
    }
  }
  return null;
}

function gripEntries(table: any): Partial<Record<GripId, Entry>> {
  const byId: Partial<Record<GripId, Entry>> = {};
  for (const i of Object.keys(table)) {
    let e: any;
    try { e = table[i]; } catch { continue; }
    if (e && typeof e === "object" && (IDS as readonly string[]).includes(e.id)) byId[e.id as GripId] = e;
  }
  return byId;
}

/** Steam's row predicate as far as the grips are concerned: every caps_filter bit set, not hidden everywhere. */
function passes(e: Entry, caps: bigint): boolean {
  const cf = BigInt(e.caps_filter ?? 0);
  return (caps & cf) === cf && (e.source_filter ?? 0) !== HIDE_IN_ALL_SOURCES;
}

function restore(byId: Record<GripId, Entry>, orig: Record<GripId, Saved>) {
  for (const id of IDS) {
    byId[id].caps_filter = orig[id].caps_filter;
    if (orig[id].source_filter === null) delete byId[id].source_filter;
    else byId[id].source_filter = orig[id].source_filter;
  }
}

const isAlly = (c: any) => c && PIDS.includes(c.unProductID) && typeof c.unCapabilities === "bigint";
function clampOne(c: any) {
  if (isAlly(c) && c.unCapabilities & GRIPS) c.unCapabilities &= ~GRIPS;
}
function clampList(l: any) {
  if (Array.isArray(l)) for (const c of l) clampOne(c);
}

const fail = (stage: string, error: string): UiPatchResult => ({ ok: false, stage, error });

export function applyLayoutPatch(): UiPatchResult {
  if (window.__allyFixLayout) return window.__allyFixLayout.result;
  const r = webpackRequire();
  if (!r?.m) return fail("webpack", "module registry not reachable");

  // ---- stage 1: metadata table, all-or-nothing ---------------------------------
  const found = findExport(r, "source_filter", (t) => {
    const g = gripEntries(t);
    return IDS.every((id) => g[id]);
  });
  if (!found) return fail("metadata", "button table not found");
  const byId = gripEntries(found.value) as Record<GripId, Entry>;
  if (IDS.filter((id) => passes(byId[id], STOCK_CAPS)).length !== 4) return fail("metadata", "stock filters look different");
  const orig = {} as Record<GripId, Saved>;
  for (const id of IDS) orig[id] = { caps_filter: byId[id].caps_filter, source_filter: byId[id].source_filter ?? null };

  byId.LeftGrip_Upper.caps_filter = UPPERGRIPS;
  byId.RightGrip_Upper.caps_filter = UPPERGRIPS;
  byId.LeftGrip.caps_filter = UPPERGRIPS; // keeps the section gate true…
  byId.LeftGrip.source_filter = HIDE_IN_ALL_SOURCES; // …without showing its row

  // Self-check: with the bit clamped exactly the upper pair must survive the filters.
  // Anything else means Steam's predicates changed under us — put the table back.
  const visible = IDS.filter((id) => passes(byId[id], STOCK_CAPS & ~GRIPS));
  if (visible.length !== 2 || !visible.every((id) => id.endsWith("_Upper"))) {
    restore(byId, orig);
    return fail("selfcheck", `rows after patch: ${visible.join(",") || "none"}`);
  }

  // ---- stage 2: clamp the bit, only now -------------------------------------------
  const storeHit = findExport(r, "m_unboundControllerList", (v) => typeof v.GetControllers === "function" && v.m_controllerList !== undefined);
  if (!storeHit) {
    restore(byId, orig);
    return fail("clamp", "controller store not found");
  }
  const cstore = storeHit.value;
  const wrapped: Record<string, (...args: any[]) => any> = {};
  for (const name of GETTERS) {
    const orig = cstore[name];
    if (typeof orig !== "function") continue;
    const fn = function (this: any, ...args: any[]) {
      const res = orig.apply(this, args);
      clampList(this?.m_controllerList);
      if (Array.isArray(res)) clampList(res);
      else clampOne(res);
      return res;
    };
    Object.defineProperty(cstore, name, { value: fn, writable: true, configurable: true, enumerable: false });
    wrapped[name] = fn;
  }
  clampList(cstore.m_controllerList);
  clampList(cstore.m_unboundControllerList);

  const caps = (cstore.m_controllerList ?? []).filter(isAlly).map((c: any) => "0x" + c.unCapabilities.toString(16));
  const result: UiPatchResult = { ok: true, module: found.moduleId, wrapped: Object.keys(wrapped), caps };
  window.__allyFixLayout = { byId, orig, store: cstore, wrapped, result };
  return result;
}

export function revertLayoutPatch(): boolean {
  const p = window.__allyFixLayout;
  if (!p) return false;
  restore(p.byId, p.orig);
  for (const [name, fn] of Object.entries(p.wrapped)) {
    // the original lives on the prototype; deleting the own property uncovers it
    if (Object.getOwnPropertyDescriptor(p.store, name)?.value === fn) delete p.store[name];
  }
  for (const l of [p.store.m_controllerList, p.store.m_unboundControllerList]) {
    if (Array.isArray(l)) for (const c of l) if (isAlly(c) && !(c.unCapabilities & GRIPS)) c.unCapabilities |= GRIPS;
  }
  delete window.__allyFixLayout;
  return true;
}

// ---- keeping the UI half in step with the toggle -------------------------------------
let syncing = false;
let again = false;
let lastWant: boolean | null = null;
let failed = false; // a failed attempt is not retried until the wanted state flips

/** Apply or revert to match the fix's enabled flag in the store; report the outcome to the backend. */
export async function syncLayoutPatch(): Promise<void> {
  if (syncing) {
    again = true;
    return;
  }
  syncing = true;
  try {
    do {
      again = false;
      const st = store.get()?.fixes.gamepad_layout;
      if (!st) continue;
      // Only on top of a native half that is in place: with the drop-in missing, hiding
      // L5/R5 alone would leave the trackpads and the four-button diagram out of step.
      const native = (st.details as Partial<GamepadLayoutDetails>).native_ready === true;
      const want = st.enabled && st.supported && native;
      const have = !!window.__allyFixLayout;
      if (want !== lastWant) {
        lastWant = want;
        failed = false;
      }
      if (want === have || failed) continue;
      if (want) {
        const result = applyLayoutPatch();
        failed = !result.ok;
        console.log("[Ally Fix] gamepad layout UI patch", result);
        await reportGamepadLayoutUi(result);
      } else {
        revertLayoutPatch();
        await reportGamepadLayoutUi(null);
      }
    } while (again);
  } catch (e) {
    console.error("[Ally Fix] gamepad layout sync failed", e);
  } finally {
    syncing = false;
  }
}

/** Plugin unload: leave Steam as we found it (a reload applies again from the settings). */
export function stopLayoutPatch(): void {
  if (revertLayoutPatch()) void reportGamepadLayoutUi(null).catch(() => undefined);
}
