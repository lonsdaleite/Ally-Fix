import { PanelSectionRow } from "@decky/ui";
import type { FixStatus } from "../types";

export function GyroExtras({ status }: { status: FixStatus }) {
  const d = status.details as { targets?: string[]; deck_uhid?: boolean; override?: string };
  return (
    <PanelSectionRow>
      <div style={{ fontSize: "0.8em", opacity: 0.7, lineHeight: 1.5 }}>
        InputPlumber target: {d.targets?.length ? d.targets.join(", ") : "unknown"}
        {d.deck_uhid === false && (d.targets?.length ?? 0) > 0 && (
          <span style={{ color: "#fbbf24" }}> — the fix only works with the deck-uhid target</span>
        )}
        <br />
        Override: {d.override ?? "?"}
        <br />
        Applying restarts InputPlumber (controller reconnects for a moment). Yaw through DualSense (ds5)
        targets becomes inverted while this fix is on.
      </div>
    </PanelSectionRow>
  );
}
