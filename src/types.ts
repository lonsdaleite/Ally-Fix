export type FixId = "cpu_boost" | "vibration" | "fan" | "gyro";
export const FIX_IDS: FixId[] = ["cpu_boost", "vibration", "fan", "gyro"];

export type FixState = "applied" | "not_applied" | "not_supported" | "error" | "stale";

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
}

export interface PluginStatus {
  version: string;
  board: string;
  product: string;
  device_supported: boolean;
  fixes: Record<FixId, FixStatus>;
  options: {
    cpu_boost: CpuBoostOptions;
    vibration: VibrationOptions;
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
    description: "Disables CPU boost and keeps the frequency cap applied after charger events.",
  },
  vibration: {
    title: "Vibration Fix",
    description: "Lowers grip-motor vibration intensity (default 50 %) and re-applies it after sleep.",
  },
  fan: {
    title: "Fan Noise Fix",
    description: "Pins the current profile's fan curve so fans cannot get stuck at full speed after resume.",
  },
  gyro: {
    title: "Gyro Fix",
    description: "Un-inverts gyro yaw in Steam Input (deck-uhid target) via an InputPlumber override.",
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
