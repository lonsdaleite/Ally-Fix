import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { useQuickAccessVisible } from "@decky/api";
import { useEffect, useState } from "react";
import { store, usePluginStatus } from "../store";
import { GYRO_MODES } from "../types";
import { CpuBoostExtras } from "./CpuBoostExtras";
import { EnhancedVibrationRow, TriggerMirrorRow } from "./VibrationToggleRows";
import { FanExtras } from "./FanExtras";
import { FixAllButton } from "./FixAllButton";
import { FixCard } from "./FixCard";
import { GyroExtras } from "./GyroExtras";
import { VibrationExtras } from "./VibrationExtras";
import { UpdateRow } from "./UpdateRow";

export function AllyFixPanel() {
  const status = usePluginStatus();
  const visible = useQuickAccessVisible();
  // One flag for the whole gyro card: the toggle and the mode dropdown must not run at once.
  const [gyroBusy, setGyroBusy] = useState(false);

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
  const ffError = (f.vibration.details as { ff_error?: string }).ff_error;
  const fanExtra = (f.fan.details as { profile?: string }).profile;
  const cpuExtra = f.cpu_boost.enabled && !status.options.cpu_boost.refresh_on_charger ? "charger refresh off" : undefined;
  const gyroExtra = GYRO_MODES.find((m) => m.data === status.options.gyro.mode)?.label;

  return (
    <>
      {!status.device_supported && (
        <PanelSection>
          <PanelSectionRow>
            <Field
              label="Unsupported device"
              description="Made for the ROG Xbox Ally X. Use at your own risk."
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
        preSettings={
          status.device_supported ? (
            <>
              <EnhancedVibrationRow enhanced={vib.enhanced} />
              {status.impulse_triggers && <TriggerMirrorRow mirror={vib.mirror_triggers} />}
              {ffError && (
                <PanelSectionRow>
                  <div style={{ fontSize: "0.8em", color: "#ff9a9a" }}>Rumble filter: {ffError}</div>
                </PanelSectionRow>
              )}
            </>
          ) : undefined
        }
      >
        <VibrationExtras options={vib} status={f.vibration} />
      </FixCard>
      <FixCard id="fan" status={f.fan} extra={fanExtra}>
        <FanExtras status={f.fan} />
      </FixCard>
      <FixCard id="gyro" status={f.gyro} extra={gyroExtra} locked={gyroBusy} onBusy={setGyroBusy}>
        <GyroExtras options={status.options.gyro} status={f.gyro} locked={gyroBusy} onBusy={setGyroBusy} />
      </FixCard>
      <FixCard id="gamepad_layout" status={f.gamepad_layout} />
      <UpdateRow version={status.version} device={status.product || status.board} />
    </>
  );
}
