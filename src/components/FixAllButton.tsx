import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { fixAll } from "../api";
import { store } from "../store";
import { FIX_IDS, type PluginStatus } from "../types";

export function FixAllButton({ status }: { status: PluginStatus }) {
  const [busy, setBusy] = useState(false);
  const supported = FIX_IDS.filter((id) => status.fixes[id]?.supported);
  const fixesOn = supported.length > 0 && supported.every((id) => status.fixes[id].enabled && status.fixes[id].state === "applied");
  // "Fix all" also brings the sub-settings back to their defaults, so it stays available
  // while any of them differs.
  const defaultsOn =
    (!status.fixes.cpu_boost.supported || status.options.cpu_boost.refresh_on_charger) &&
    (!status.fixes.vibration.supported ||
      (status.options.vibration.left === 50 && status.options.vibration.right === 50));
  const allOn = fixesOn && defaultsOn;

  const onClick = async () => {
    setBusy(true);
    try {
      const next = await fixAll();
      store.set(next);
      const applied = FIX_IDS.filter((id) => next.fixes[id]?.state === "applied").length;
      toaster.toast({ title: "Ally Fix", body: `Applied ${applied} of ${supported.length} fixes` });
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
