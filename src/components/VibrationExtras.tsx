import { ButtonItem, PanelSectionRow, SliderField, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import { setVibrationOptions, testVibration } from "../api";
import { store } from "../store";
import type { FixStatus, VibrationOptions } from "../types";

const DEBOUNCE_MS = 200;

export function VibrationExtras({ options, status }: { options: VibrationOptions; status: FixStatus }) {
  const off = !status.enabled;
  const hw = status.details as { hw_left?: number | null; hw_right?: number | null };
  // While the fix is off the sliders mirror what the hardware currently has and are read-only.
  const shown: VibrationOptions = off
    ? {
        left: Math.min(100, hw.hw_left ?? 100),
        right: Math.min(100, hw.hw_right ?? 100),
        linked: (hw.hw_left ?? 100) === (hw.hw_right ?? 100),
        enhanced: options.enhanced,
        mirror_triggers: options.mirror_triggers,
      }
    : options;
  const [local, setLocal] = useState<VibrationOptions>(shown);
  const timer = useRef<number | undefined>(undefined);
  const pending = useRef(false); // a slider edit not yet acknowledged by the backend

  useEffect(() => {
    if (!pending.current) setLocal(shown);
  }, [shown.left, shown.right, shown.linked, off]);

  const push = (next: VibrationOptions) => {
    setLocal(next);
    const cur = store.get();
    if (cur) store.set({ ...cur, options: { ...cur.options, vibration: next } });
    pending.current = true;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      try {
        const res = await setVibrationOptions(next);
        if (res.status) store.patchFix(res.status);
      } finally {
        pending.current = false;
      }
    }, DEBOUNCE_MS);
  };

  const onTest = async () => {
    const res = await testVibration(500);
    if (!res.ok) toaster.toast({ title: "Vibration Fix", body: res.error });
  };

  return (
    <>
      <PanelSectionRow>
        <ToggleField
          label="Link both motors"
          disabled={off}
          checked={local.linked}
          onChange={(linked) => push({ ...local, linked, right: linked ? local.left : local.right })}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <SliderField
          label={local.linked ? "Intensity" : "Left motor"}
          value={local.left}
          disabled={off}
          min={0}
          max={100}
          step={1}
          showValue
          onChange={(left) => push({ ...local, left, right: local.linked ? left : local.right })}
        />
      </PanelSectionRow>
      {!local.linked && (
        <PanelSectionRow>
          <SliderField
            label="Right motor"
            value={local.right}
            disabled={off}
            min={0}
            max={100}
            step={1}
            showValue
            onChange={(right) => push({ ...local, right })}
          />
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onTest}>
          Test vibration (0.5 s)
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ fontSize: "0.8em", opacity: 0.7 }}>
          Motor strength in percent, written straight to the controller. Turning the fix on sets 50/50; turning it off restores the firmware default 100/100. Grip motors only.
        </div>
      </PanelSectionRow>
    </>
  );
}
