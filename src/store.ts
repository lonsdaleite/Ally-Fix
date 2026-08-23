import { useEffect, useState } from "react";
import { addEventListener, removeEventListener } from "@decky/api";
import { getStatus } from "./api";
import type { FixStatus, PluginStatus } from "./types";

type Listener = () => void;

let cache: PluginStatus | null = null;
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((l) => l());
}

export const store = {
  get(): PluginStatus | null {
    return cache;
  },
  set(status: PluginStatus) {
    cache = status;
    notify();
  },
  patchFix(fix: FixStatus) {
    if (!cache) return;
    cache = { ...cache, fixes: { ...cache.fixes, [fix.id]: fix } };
    notify();
  },
  async refresh() {
    try {
      store.set(await getStatus());
    } catch (e) {
      console.error("[Ally Fix] get_status failed", e);
    }
  },
  subscribe(l: Listener): () => void {
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  },
};

const onFixStatus = (fix: FixStatus) => store.patchFix(fix);
const onStatus = (status: PluginStatus) => store.set(status);

export function connectEvents() {
  addEventListener<[FixStatus]>("fix_status", onFixStatus);
  addEventListener<[PluginStatus]>("status", onStatus);
  void store.refresh();
}

export function disconnectEvents() {
  removeEventListener("fix_status", onFixStatus);
  removeEventListener("status", onStatus);
}

export function usePluginStatus(): PluginStatus | null {
  const [state, setState] = useState<PluginStatus | null>(cache);
  useEffect(() => store.subscribe(() => setState(cache)), []);
  return state;
}
