import { callable } from "@decky/api";
import type {
  ActionResult,
  CpuBoostOptions,
  FixId,
  PluginStatus,
  SimpleResult,
  VibrationOptions,
} from "./types";

export const getStatus = callable<[], PluginStatus>("get_status");
export const setFixEnabled = callable<[fix_id: FixId, enabled: boolean], ActionResult>("set_fix_enabled");
export const fixAll = callable<[], PluginStatus>("fix_all");
export const setCpuBoostOptions = callable<[opts: Partial<CpuBoostOptions>], ActionResult>("set_cpu_boost_options");
export const cpuCapRefreshNow = callable<[], SimpleResult>("cpu_cap_refresh_now");
export const setVibrationOptions = callable<[opts: Partial<VibrationOptions>], ActionResult>("set_vibration_options");
export const testVibration = callable<[duration_ms: number], SimpleResult>("test_vibration");
export const fanRestoreFactoryCurve = callable<[], ActionResult>("fan_restore_factory_curve");
