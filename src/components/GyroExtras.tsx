import { DropdownItem, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { setGyroOptions } from "../api";
import { confirm, gyroNeedsSteamRestart, restartSteam, RESTART_TEXT } from "../steamRestart";
import { store } from "../store";
import { GYRO_MODES, type FixStatus, type GyroMode, type GyroOptions } from "../types";

export function GyroExtras({
  options,
  status,
  locked,
  onBusy,
}: {
  options: GyroOptions;
  status: FixStatus;
  locked: boolean; // another action on this fix is running
  onBusy: (busy: boolean) => void;
}) {
  const [busy, setBusyState] = useState(false);
  // Steam's dropdown keeps the option the user picked in its own state; when the change is
  // declined nothing in the store moves, so remount it to show the real value again.
  const [rev, setRev] = useState(0);
  const d = status.details as { targets?: string[]; deck_uhid?: boolean };
  const inactive = d.deck_uhid === false && (d.targets?.length ?? 0) > 0;
  const current = GYRO_MODES.find((m) => m.data === options.mode) ?? GYRO_MODES[0];

  const setBusy = (b: boolean) => {
    setBusyState(b);
    onBusy(b);
  };
  const setMode = (mode: GyroMode) => {
    const cur = store.get();
    if (cur) store.set({ ...cur, options: { ...cur.options, gyro: { ...cur.options.gyro, mode } } });
  };

  const onChange = async (mode: GyroMode) => {
    if (busy || locked || mode === options.mode) return;
    const cur = store.get();
    // Nothing is touched until the user agrees: with the fix on, a mode change that adds
    // or removes the steam_dev.cfg line only makes sense together with a Steam restart.
    const restart = !!cur && status.enabled && gyroNeedsSteamRestart(cur, true, mode);
    if (restart) {
      const label = GYRO_MODES.find((m) => m.data === mode)?.label ?? mode;
      const choice = await confirm({
        title: `Switch to ${label}?`,
        description: RESTART_TEXT,
        ok: "Apply and restart Steam",
      });
      if (choice !== "ok") {
        setRev((r) => r + 1);
        return;
      }
    }
    setBusy(true);
    setMode(mode);
    try {
      const res = await setGyroOptions({ mode });
      if (res.status) store.patchFix(res.status);
      if (!res.ok) {
        toaster.toast({ title: "Gyro Fix", body: res.error || "Mode change failed" });
      } else if (restart) {
        restartSteam();
      }
    } catch (e) {
      setMode(options.mode);
      setRev((r) => r + 1);
      toaster.toast({ title: "Gyro Fix", body: String(e) });
    } finally {
      setBusy(false);
      await store.refresh();
    }
  };

  return (
    <>
      <PanelSectionRow>
        <DropdownItem
          key={rev}
          label="Mode"
          description={current.description}
          rgOptions={GYRO_MODES.map((m) => ({ data: m.data, label: m.label }))}
          selectedOption={options.mode}
          disabled={busy || locked}
          onChange={(o) => void onChange(o.data as GyroMode)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ fontSize: "0.8em", opacity: 0.7, lineHeight: 1.5 }}>
          Turning it on or off, or changing the mode, reconnects the controller for a moment.
          {inactive && <span style={{ color: "#fbbf24" }}> Not active with this controller setup.</span>}
        </div>
      </PanelSectionRow>
    </>
  );
}
