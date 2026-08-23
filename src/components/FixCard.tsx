import { PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState, type ReactNode } from "react";
import { setFixEnabled } from "../api";
import { store } from "../store";
import { FIX_LABELS, type FixId, type FixStatus } from "../types";
import { Collapsible } from "./Collapsible";
import { StatusLine } from "./StatusLine";

export function FixCard({
  id,
  status,
  extra,
  children,
}: {
  id: FixId;
  status: FixStatus;
  extra?: string;
  children?: ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  const { title, description } = FIX_LABELS[id];

  const onToggle = async (enabled: boolean) => {
    setBusy(true);
    store.patchFix({ ...status, enabled });
    try {
      const res = await setFixEnabled(id, enabled);
      if (res.status) store.patchFix(res.status);
      if (!res.ok) toaster.toast({ title, body: res.error || "Failed" });
      await store.refresh(); // options (sub-settings) may have been reset by the backend
    } catch (e) {
      store.patchFix(status);
      toaster.toast({ title, body: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelSection title={title}>
      <PanelSectionRow>
        <ToggleField
          label="Enable"
          description={description}
          checked={status.enabled}
          disabled={busy || !status.supported}
          onChange={onToggle}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <StatusLine status={status} extra={extra} />
      </PanelSectionRow>
      {children && status.supported && <Collapsible title="Settings">{children}</Collapsible>}
    </PanelSection>
  );
}
