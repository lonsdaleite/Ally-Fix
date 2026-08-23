import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { useQuickAccessVisible } from "@decky/api";
import { useEffect } from "react";
import { store, usePluginStatus } from "../store";
import { CpuBoostExtras } from "./CpuBoostExtras";
import { EnhancedVibrationRow } from "./EnhancedVibrationRow";
import { FanExtras } from "./FanExtras";
import { FixAllButton } from "./FixAllButton";
import { FixCard } from "./FixCard";
import { GyroExtras } from "./GyroExtras";
import { VibrationExtras } from "./VibrationExtras";
import { UpdateRow } from "./UpdateRow";

export function AllyFixPanel() {
  const status = usePluginStatus();
  const visible = useQuickAccessVisible();

  useEffect(() => {
    if (!visible) return;
    void store.refresh();
    const id = window.setInterval(() => void store.refresh(), 5000);
    return () => window.clearInterval(id);
  }, [visible]);

  if (!status) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field label="Loading…" focusable={false} />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const f = status.fixes;
  const vib = status.options.vibration;
  const hw = f.vibration.details as { hw_left?: number | null; hw_right?: number | null };
  const vibExtra =
    hw.hw_left != null && hw.hw_right != null
      ? hw.hw_left === hw.hw_right
        ? `now ${hw.hw_left}`
        : `now ${hw.hw_left}/${hw.hw_right}`
      : undefined;
  const fanExtra = (f.fan.details as { profile?: string }).profile;
  const cpuExtra = f.cpu_boost.enabled && !status.options.cpu_boost.refresh_on_charger ? "charger refresh off" : undefined;

  return (
    <>
      {!status.device_supported && (
        <PanelSection>
          <PanelSectionRow>
            <Field
              label="Unsupported device"
              description={`These fixes are made for the ROG Xbox Ally X (board ${status.board || "unknown"}). Use at your own risk.`}
              focusable={false}
            />
          </PanelSectionRow>
        </PanelSection>
      )}
      <FixAllButton status={status} />
      <FixCard id="cpu_boost" status={f.cpu_boost} extra={cpuExtra}>
        <CpuBoostExtras options={status.options.cpu_boost} status={f.cpu_boost} />
      </FixCard>
      <FixCard
        id="vibration"
        status={f.vibration}
        extra={vibExtra}
        preSettings={status.device_supported ? <EnhancedVibrationRow enhanced={vib.enhanced} /> : undefined}
      >
        <VibrationExtras options={vib} status={f.vibration} />
      </FixCard>
      <FixCard id="fan" status={f.fan} extra={fanExtra}>
        <FanExtras status={f.fan} />
      </FixCard>
      <FixCard id="gyro" status={f.gyro}>
        <GyroExtras status={f.gyro} />
      </FixCard>
      <UpdateRow version={status.version} device={status.product || status.board} />
    </>
  );
}
