import { PanelSectionRow } from "@decky/ui";
import type { FixStatus } from "../types";

export function GyroExtras({ status }: { status: FixStatus }) {
  const d = status.details as { targets?: string[]; deck_uhid?: boolean };
  const inactive = d.deck_uhid === false && (d.targets?.length ?? 0) > 0;
  return (
    <PanelSectionRow>
      <div style={{ fontSize: "0.8em", opacity: 0.7, lineHeight: 1.5 }}>
        Turning it on or off reconnects the controller for a moment.
        {inactive && <span style={{ color: "#fbbf24" }}> Not active with this controller setup.</span>}
      </div>
    </PanelSectionRow>
  );
}
