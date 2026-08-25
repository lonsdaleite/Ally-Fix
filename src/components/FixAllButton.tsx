import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { fixAll } from "../api";
import { confirm, gyroNeedsSteamRestart, restartSteam, steamCfgPresent } from "../steamRestart";
import { store } from "../store";
import { FIX_IDS, type FixId, type PluginStatus } from "../types";

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
    // Nothing is touched before the answer: enabling the Gyro Fix in Complex mode changes
    // Steam's steam_dev.cfg, which Steam reads only at start-up.
    const skip: FixId[] = [];
    let restart = false;
    if (status.fixes.gyro.supported && gyroNeedsSteamRestart(status, true, status.options.gyro.mode)) {
      const d = await confirm({
        title: "Fix all",
        description:
          "The Gyro Fix in its current mode needs a Steam restart. Apply everything and restart Steam now, or apply the other fixes and leave the Gyro Fix as it is?",
        ok: "Apply and restart Steam",
        middle: "Skip Gyro Fix",
      });
      if (d === "cancel") return;
      if (d === "middle") skip.push("gyro");
      restart = d === "ok";
    }
    setBusy(true);
    try {
      const next = await fixAll(skip);
      store.set(next);
      const applied = FIX_IDS.filter((id) => next.fixes[id]?.state === "applied").length;
      toaster.toast({ title: "Ally Fix", body: `Applied ${applied} of ${supported.length} fixes` });
      // Restart only if the gyro step actually changed steam_dev.cfg.
      if (restart && next.fixes.gyro.state === "applied" && steamCfgPresent(next)) restartSteam();
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
