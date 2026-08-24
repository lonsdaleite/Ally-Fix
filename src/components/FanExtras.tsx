import { ButtonItem, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { fanRestoreFactoryCurve } from "../api";
import { store } from "../store";
import type { FixStatus } from "../types";

export function FanExtras({ status }: { status: FixStatus }) {
  const d = status.details as { rpm?: (number | null)[]; temp?: number | null };
  const onRestore = async () => {
    const res = await fanRestoreFactoryCurve();
    if (res.status) store.patchFix(res.status);
    toaster.toast({ title: "Fan Noise Fix", body: res.ok ? res.message || "Factory curve restored" : res.error });
  };
  return (
    <>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onRestore}>
          Reset fan curve
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ fontSize: "0.8em", opacity: 0.7, lineHeight: 1.5 }}>
          CPU fan: {d.rpm?.[0] ?? "?"} rpm · GPU fan: {d.rpm?.[1] ?? "?"} rpm
          {d.temp != null && ` · CPU ${Math.round(d.temp)}°C`}
        </div>
      </PanelSectionRow>
    </>
  );
}
