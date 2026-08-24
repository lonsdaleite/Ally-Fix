import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { checkUpdate, installUpdate } from "../api";
import type { UpdateInfo } from "../types";

export function UpdateRow({ version, device }: { version: string; device: string }) {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [busy, setBusy] = useState(false);

  const onCheck = async () => {
    setBusy(true);
    try {
      const res = await checkUpdate();
      setInfo(res);
      if (!res.ok) toaster.toast({ title: "Ally Fix", body: res.error });
      else if (res.update_available) toaster.toast({ title: "Ally Fix", body: `v${res.latest} is available` });
      else toaster.toast({ title: "Ally Fix", body: `v${version} is the latest version` });
    } finally {
      setBusy(false);
    }
  };

  const onInstall = async () => {
    if (!info?.zip) return;
    setBusy(true);
    const res = await installUpdate(info.zip);
    if (res.ok) toaster.toast({ title: "Ally Fix", body: `Updating to ${info.latest}… Decky will restart` });
    else {
      toaster.toast({ title: "Ally Fix", body: res.error });
      setBusy(false);
    }
  };

  return (
    <PanelSection title="Updates">
      <PanelSectionRow>
        {info?.ok && info.update_available ? (
          <ButtonItem layout="below" disabled={busy} onClick={onInstall}>
            Update to {info.latest}
          </ButtonItem>
        ) : (
          <ButtonItem layout="below" disabled={busy} onClick={onCheck}>
            Check for updates
          </ButtonItem>
        )}
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ fontSize: "0.75em", opacity: 0.5, textAlign: "center" }}>
          Ally Fix v{version}
          {info?.ok && info.latest ? ` (latest ${info.latest})` : ""} · {device}
        </div>
      </PanelSectionRow>
    </PanelSection>
  );
}
