import { PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { setEnhancedVibration } from "../api";
import { store } from "../store";

// Independent of the intensity fix: the flag lives in the controller's MCU and
// survives reboots, so this row is never disabled by the fix's Enable toggle.
export function EnhancedVibrationRow({ enhanced }: { enhanced: boolean }) {
  const [busy, setBusy] = useState(false);

  const patch = (value: boolean) => {
    const cur = store.get();
    if (cur)
      store.set({
        ...cur,
        options: { ...cur.options, vibration: { ...cur.options.vibration, enhanced: value } },
      });
  };

  const onToggle = async (on: boolean) => {
    setBusy(true);
    patch(on);
    try {
      const res = await setEnhancedVibration(on);
      if (!res.ok) {
        patch(enhanced);
        toaster.toast({ title: "Enhanced Vibration", body: res.error || "Failed" });
      }
    } catch (e) {
      patch(enhanced);
      toaster.toast({ title: "Enhanced Vibration", body: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelSectionRow>
      <ToggleField
        label="Enhanced Vibration"
        description="Xbox-recommended waveform (same as the Armoury Crate toggle). Stored in the controller, survives reboots. Independent of the fix above."
        checked={enhanced}
        disabled={busy}
        onChange={onToggle}
      />
    </PanelSectionRow>
  );
}
