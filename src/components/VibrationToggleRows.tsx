import { PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { setEnhancedVibration, setTriggerMirror } from "../api";
import { store } from "../store";
import type { ActionResult, VibrationOptions } from "../types";

type FlagKey = "enhanced" | "mirror_triggers";

// Rows that live above the Settings collapsible and are independent of the
// intensity fix, so they are never disabled by the fix's Enable toggle.
function FlagRow({
  flag,
  checked,
  label,
  description,
  call,
}: {
  flag: FlagKey;
  checked: boolean;
  label: string;
  description: string;
  call: (on: boolean) => Promise<ActionResult>;
}) {
  const [busy, setBusy] = useState(false);

  const patch = (value: boolean) => {
    const cur = store.get();
    if (cur) {
      const vibration: VibrationOptions = { ...cur.options.vibration, [flag]: value };
      store.set({ ...cur, options: { ...cur.options, vibration } });
    }
  };

  const onToggle = async (on: boolean) => {
    setBusy(true);
    patch(on);
    try {
      const res = await call(on);
      if (res.status) store.patchFix(res.status);
      if (!res.ok) {
        patch(checked);
        toaster.toast({ title: label, body: res.error || "Failed" });
      }
    } catch (e) {
      patch(checked);
      toaster.toast({ title: label, body: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelSectionRow>
      <ToggleField label={label} description={description} checked={checked} disabled={busy} onChange={onToggle} />
    </PanelSectionRow>
  );
}

// The flag lives in the controller's MCU and survives reboots.
export function EnhancedVibrationRow({ enhanced }: { enhanced: boolean }) {
  return (
    <FlagRow
      flag="enhanced"
      checked={enhanced}
      label="Enhanced Vibration"
      description="Xbox-recommended waveform (same as the Armoury Crate toggle). Stored in the controller, survives reboots. Independent of the fix above. Game rumble is capped at the controller's full scale while on, so full-strength rumble does not rattle."
      call={setEnhancedVibration}
    />
  );
}

// Host-side rewrite of the driver's rumble packets (Xbox Ally X only).
export function TriggerMirrorRow({ mirror }: { mirror: boolean }) {
  return (
    <FlagRow
      flag="mirror_triggers"
      checked={mirror}
      label="Mirror to triggers"
      description="Mirror grip rumble onto the impulse triggers at the same strength (left grip → LT, right grip → RT). Works in every game; nothing is stored in the controller."
      call={setTriggerMirror}
    />
  );
}
