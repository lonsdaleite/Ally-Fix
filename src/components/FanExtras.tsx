import { ButtonItem, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { fanRestoreFactoryCurve } from "../api";
import { store } from "../store";
import type { FixStatus } from "../types";

export function FanExtras({ status }: { status: FixStatus }) {
  const d = status.details as {
    profile?: string;
    pwm_enable?: (number | null)[];
    rpm?: (number | null)[];
    temp?: number | null;
    snapshot_profiles?: string[];
    last_event?: string;
  };
  const onRestore = async () => {
    const res = await fanRestoreFactoryCurve();
    if (res.status) store.patchFix(res.status);
    toaster.toast({ title: "Fan Noise Fix", body: res.ok ? res.message || "Factory curve restored" : res.error });
  };
  return (
    <>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onRestore}>
          Restore factory curve for this profile
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ fontSize: "0.8em", opacity: 0.7, lineHeight: 1.5 }}>
          Profile: {d.profile ?? "?"} · mode: {d.pwm_enable?.join("/") ?? "?"}
          <br />
          CPU fan: {d.rpm?.[0] ?? "?"} rpm · GPU fan: {d.rpm?.[1] ?? "?"} rpm
          {d.temp != null && ` · CPU ${Math.round(d.temp)}°C`}
          <br />
          Curves remembered for: {d.snapshot_profiles?.length ? d.snapshot_profiles.join(", ") : "none yet"}
          {d.last_event && (
            <>
              <br />
              Last: {d.last_event}
            </>
          )}
          <br />
          The fix pins whatever curve the current profile uses (factory curve unless another tool changed it).
          Use the button above only to discard a curve written by another tool.
        </div>
      </PanelSectionRow>
    </>
  );
}
