import { ButtonItem, PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { cpuCapRefreshNow, setCpuBoostOptions } from "../api";
import { store } from "../store";
import type { CpuBoostOptions, FixStatus } from "../types";

export function CpuBoostExtras({ options, status }: { options: CpuBoostOptions; status: FixStatus }) {
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
          description="Keep boost off when plugging the charger in or out."
          checked={status.enabled && options.refresh_on_charger}
          disabled={!status.enabled}
          onChange={onToggle}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={!status.enabled} onClick={onRefresh}>
          Apply now
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}
