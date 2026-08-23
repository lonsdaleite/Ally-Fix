import { ButtonItem, PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { cpuCapRefreshNow, setCpuBoostOptions } from "../api";
import { store } from "../store";
import type { CpuBoostOptions, FixStatus } from "../types";

export function CpuBoostExtras({ options, status }: { options: CpuBoostOptions; status: FixStatus }) {
  const d = status.details as { over_cap_cores?: number; policies?: number; kicks?: number };
  const onToggle = async (refresh_on_charger: boolean) => {
    const cur = store.get();
    if (cur) store.set({ ...cur, options: { ...cur.options, cpu_boost: { ...cur.options.cpu_boost, refresh_on_charger } } });
    const res = await setCpuBoostOptions({ refresh_on_charger });
    if (res.status) store.patchFix(res.status);
  };
  const onRefresh = async () => {
    const res = await cpuCapRefreshNow();
    toaster.toast({ title: "CPU Boost Fix", body: res.ok ? "Refreshing CPU cap…" : res.error });
  };
  return (
    <>
      <PanelSectionRow>
        <ToggleField
          label="Refresh cap on charger events"
          description="Re-applies the frequency cap when the charger is plugged or unplugged (the firmware drops it otherwise). Turning the fix on resets this to enabled."
          checked={status.enabled && options.refresh_on_charger}
          disabled={!status.enabled}
          onChange={onToggle}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={!status.enabled} onClick={onRefresh}>
          Refresh cap now
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ fontSize: "0.8em", opacity: 0.7 }}>
          Cores over cap: {d.over_cap_cores ?? "?"} / {d.policies ?? "?"} · kicks: {d.kicks ?? 0}
        </div>
      </PanelSectionRow>
    </>
  );
}
