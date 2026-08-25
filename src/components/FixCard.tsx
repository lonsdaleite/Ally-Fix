import { PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState, type ReactNode } from "react";
import { setFixEnabled } from "../api";
import { confirm, RESTART_RULES, restartSteam } from "../steamRestart";
import { store } from "../store";
import { FIX_LABELS, type FixId, type FixStatus } from "../types";
import { Collapsible } from "./Collapsible";
import { StatusLine } from "./StatusLine";

type Decision = "ok" | "ok-restart" | "cancel";

export function FixCard({
  id,
  status,
  extra,
  preSettings,
  locked,
  onBusy,
  children,
}: {
  id: FixId;
  status: FixStatus;
  extra?: string;
  preSettings?: ReactNode; // rendered above the Settings collapsible, not gated by Enable
  locked?: boolean; // another action on this fix (e.g. a mode change) is running
  onBusy?: (busy: boolean) => void;
  children?: ReactNode;
}) {
  const [busyState, setBusyState] = useState(false);
  // The toggle keeps its own visual state; after a declined guard nothing in the store
  // moves, so remount it to show the real value again.
  const [rev, setRev] = useState(0);
  const { title, description } = FIX_LABELS[id];
  const busy = busyState || !!locked;
  const setBusy = (b: boolean) => {
    setBusyState(b);
    onBusy?.(b);
  };

  const onToggle = async (enabled: boolean) => {
    if (busy) return;
    // Nothing is touched before the answer when the change only takes effect after a
    // Steam restart (steam_dev.cfg, the LD_PRELOAD drop-in).
    let decision: Decision = "ok";
    const rule = RESTART_RULES[id];
    const cur = store.get();
    if (rule && cur && rule.needs(cur, enabled)) {
      const d = await confirm({
        title: enabled ? `Turn ${title} on?` : `Turn ${title} off?`,
        description: rule.text,
        ok: "Apply and restart Steam",
      });
      decision = d === "ok" ? "ok-restart" : "cancel";
    }
    if (decision === "cancel") {
      setRev((r) => r + 1);
      return;
    }
    setBusy(true);
    store.patchFix({ ...status, enabled });
    try {
      const res = await setFixEnabled(id, enabled);
      if (res.status) store.patchFix(res.status);
      if (!res.ok) toaster.toast({ title, body: res.error || "Failed" });
      await store.refresh(); // options (sub-settings) may have been reset by the backend
      if (res.ok && decision === "ok-restart") void restartSteam();
    } catch (e) {
      store.patchFix(status);
      toaster.toast({ title, body: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelSection title={title}>
      <PanelSectionRow>
        <ToggleField
          key={rev}
          label="Enable"
          description={description}
          checked={status.enabled}
          disabled={busy || !status.supported}
          onChange={onToggle}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <StatusLine status={status} extra={extra} />
      </PanelSectionRow>
      {status.supported && preSettings}
      {children && status.supported && (
        <Collapsible id={`${id}-settings`} title="Settings">
          {children}
        </Collapsible>
      )}
    </PanelSection>
  );
}
