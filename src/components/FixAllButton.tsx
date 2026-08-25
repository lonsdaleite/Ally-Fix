import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { fixAll } from "../api";
import { confirm, RESTART_RULES, restartSteam } from "../steamRestart";
import { store } from "../store";
import { FIX_IDS, FIX_LABELS, type FixId, type PluginStatus } from "../types";

export function FixAllButton({ status }: { status: PluginStatus }) {
  const [busy, setBusy] = useState(false);
  const supported = FIX_IDS.filter((id) => status.fixes[id]?.supported);
  const fixesOn = supported.length > 0 && supported.every((id) => status.fixes[id].enabled && status.fixes[id].state === "applied");
  // "Fix all" also brings the sub-settings back to their defaults, so it stays available
  // while any of them differs. The gyro mode is a choice, not a default, and is kept.
  const defaultsOn =
    (!status.fixes.cpu_boost.supported || status.options.cpu_boost.refresh_on_charger) &&
    (!status.fixes.vibration.supported ||
      (status.options.vibration.left === 50 && status.options.vibration.right === 50));
  const allOn = fixesOn && defaultsOn;

  const onClick = async () => {
    // Nothing is touched before the answer: some fixes only take effect after a Steam
    // restart (the Gyro Fix in Complex mode, the Gamepad Layout Fix). One restart covers
    // all of them.
    const restartIds = supported.filter((id) => RESTART_RULES[id]?.needs(status, true));
    const skip: FixId[] = [];
    let restart = false;
    if (restartIds.length > 0) {
      const names = restartIds.map((id) => FIX_LABELS[id].title);
      const one = names.length === 1;
      const list = names.join(" and ");
      const d = await confirm({
        title: "Fix all",
        description: `${list} need${one ? "s" : ""} a Steam restart. Apply everything and restart Steam now, or apply the other fixes and leave ${one ? "it" : "them"} as ${one ? "it is" : "they are"}?`,
        ok: "Apply and restart Steam",
        middle: one ? `Skip ${list}` : "Skip those",
      });
      if (d === "cancel") return;
      if (d === "middle") skip.push(...restartIds);
      restart = d === "ok";
    }
    setBusy(true);
    try {
      const next = await fixAll(skip);
      store.set(next);
      const applied = FIX_IDS.filter((id) => ["applied", "restart_pending"].includes(next.fixes[id]?.state)).length;
      toaster.toast({ title: "Ally Fix", body: `Applied ${applied} of ${supported.length} fixes` });
      // Restart only if at least one of those fixes actually went on.
      if (restart && restartIds.some((id) => ["applied", "restart_pending"].includes(next.fixes[id].state))) void restartSteam();
    } catch (e) {
      toaster.toast({ title: "Ally Fix", body: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelSection>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy || allOn || supported.length === 0 || !status.device_supported} onClick={onClick}>
          {allOn ? "All fixes applied" : "Fix all"}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}
