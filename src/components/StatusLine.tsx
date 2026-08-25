import { Field } from "@decky/ui";
import type { FixStatus } from "../types";

const COLORS: Record<FixStatus["state"], string> = {
  applied: "#4ade80",
  not_applied: "#9ca3af",
  not_supported: "#6b7280",
  stale: "#fbbf24",
  restart_pending: "#fbbf24",
  error: "#f87171",
};

const LABELS: Record<FixStatus["state"], string> = {
  applied: "Applied",
  not_applied: "Not applied",
  not_supported: "Not supported",
  stale: "Needs update",
  restart_pending: "Restart Steam",
  error: "Error",
};

function stateText(status: FixStatus): string {
  if (status.state === "applied" && !status.enabled) return "Already in fixed state";
  if (status.state === "not_applied" && status.enabled) return "Enabled, but not applied";
  return LABELS[status.state];
}

export function StatusLine({ status, extra }: { status: FixStatus; extra?: string }) {
  const text = extra ? `${stateText(status)} · ${extra}` : stateText(status);
  const description = status.message || undefined;
  return (
    <Field
      label="Status"
      childrenLayout="inline"
      focusable={false}
      bottomSeparator="none"
      description={description}
    >
      <span style={{ display: "block", textAlign: "right", fontSize: "0.85em", opacity: 0.9 }}>
        <span
          style={{
            width: 9,
            height: 9,
            borderRadius: "50%",
            background: COLORS[status.state],
            display: "inline-block",
            marginRight: 6,
            verticalAlign: "middle",
          }}
        />
        {text}
      </span>
    </Field>
  );
}
