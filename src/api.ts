import { callable } from "@decky/api";
import type {
  ActionResult,
  CpuBoostOptions,
  FixId,
  PluginStatus,
  SimpleResult,
  UpdateInfo,
  VibrationOptions,
} from "./types";

export const getStatus = callable<[], PluginStatus>("get_status");
export const setFixEnabled = callable<[fix_id: FixId, enabled: boolean], ActionResult>("set_fix_enabled");
export const fixAll = callable<[], PluginStatus>("fix_all");
export const setCpuBoostOptions = callable<[opts: Partial<CpuBoostOptions>], ActionResult>("set_cpu_boost_options");
export const cpuCapRefreshNow = callable<[], SimpleResult>("cpu_cap_refresh_now");
export const setVibrationOptions = callable<[opts: Partial<VibrationOptions>], ActionResult>("set_vibration_options");
export const setEnhancedVibration = callable<[enabled: boolean], ActionResult>("set_enhanced_vibration");
export const setTriggerMirror = callable<[enabled: boolean], ActionResult>("set_trigger_mirror");
export const testVibration = callable<[duration_ms: number], SimpleResult>("test_vibration");
export const fanRestoreFactoryCurve = callable<[], ActionResult>("fan_restore_factory_curve");
export const checkUpdate = callable<[], UpdateInfo>("check_update");
export const installUpdate = callable<[zip_url: string], SimpleResult>("install_update");
