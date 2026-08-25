export type FixId = "cpu_boost" | "vibration" | "fan" | "gyro" | "gamepad_layout";
export const FIX_IDS: FixId[] = ["cpu_boost", "vibration", "fan", "gyro", "gamepad_layout"];

export type FixState = "applied" | "not_applied" | "not_supported" | "error" | "stale" | "restart_pending";

export interface FixStatus {
  id: FixId;
  enabled: boolean;
  state: FixState;
  supported: boolean;
  message: string;
  details: Record<string, unknown>;
}

export interface CpuBoostOptions {
  refresh_on_charger: boolean;
}

export interface VibrationOptions {
  left: number;
  right: number;
  linked: boolean;
  enhanced: boolean;
  mirror_triggers: boolean;
}

export type GyroMode = "simple" | "complex" | "deck";

export interface GyroOptions {
  mode: GyroMode;
}

export const GYRO_MODES: { data: GyroMode; label: string; description: string }[] = [
  {
    data: "simple",
    label: "Simple",
    description: "Fixes the gyro in regular games. In Valve's Source games (Portal 2, Half-Life 2) Yaw and Roll stay swapped.",
  },
  {
    data: "complex",
    label: "Complex",
    description: "Fixes the gyro everywhere. Steam has to be restarted when this mode is switched on or off.",
  },
  {
    data: "deck",
    label: "Deck Emulation",
    description: "Fixes the gyro everywhere by presenting a generic controller to Steam. Layouts saved for the ROG Ally no longer apply.",
  },
];

/** Outcome of the UI half of the Gamepad Layout Fix (see gamepadLayout.ts). */
export interface UiPatchResult {
  ok: boolean;
  stage?: string;
  error?: string;
  module?: string;
  wrapped?: string[];
  caps?: string[];
  art?: string; // "ok" or why the controller picture stayed stock
}

export interface GamepadLayoutDetails {
  native_ready: boolean; // shim copy and service drop-in are in place
  shim_active: boolean; // the native shim is loaded in the running Steam client
  shim_patched: boolean | null;
  ui: UiPatchResult | null;
  restart_pending: boolean;
}

export interface PluginStatus {
  version: string;
  board: string;
  product: string;
  device_supported: boolean;
  impulse_triggers: boolean;
  fixes: Record<FixId, FixStatus>;
  options: {
    cpu_boost: CpuBoostOptions;
    vibration: VibrationOptions;
    gyro: GyroOptions;
  };
}

export interface ActionResult {
  ok: boolean;
  error: string;
  status: FixStatus | null;
  message?: string;
}

export interface SimpleResult {
  ok: boolean;
  error: string;
}

export const FIX_LABELS: Record<FixId, { title: string; description: string }> = {
  cpu_boost: {
    title: "CPU Boost Fix",
    description: "Turns CPU boost off and keeps it off.",
  },
  vibration: {
    title: "Vibration Fix",
    description: "Softer rumble (50 %).",
  },
  fan: {
    title: "Fan Noise Fix",
    description: "Stops the fans getting stuck at full speed after sleep.",
  },
  gyro: {
    title: "Gyro Fix",
    description: "Fixes the gyro turning the wrong way in Steam Input.",
  },
  gamepad_layout: {
    title: "Gamepad Layout Fix",
    description: "Removes the trackpads, touch sticks and lower rear buttons (L5/R5) the Ally does not have from Steam Input.",
  },
};

export interface UpdateInfo {
  ok: boolean;
  error: string;
  current: string;
  latest?: string;
  url?: string;
  zip?: string;
  update_available?: boolean;
}
