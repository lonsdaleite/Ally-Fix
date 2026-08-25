import { ConfirmModal, showModal } from "@decky/ui";
import { restartSteamService } from "./api";
import type { FixId, GamepadLayoutDetails, GyroMode, PluginStatus } from "./types";

/**
 * One restart for everything that needs it. The backend restarts Steam's user service, which
 * gives the client a fresh environment (the Gamepad Layout Fix hooks in through LD_PRELOAD);
 * Steam's own restart keeps the old environment, so it is only the fallback for desktop mode,
 * where the service is not used.
 */
export async function restartSteam(): Promise<void> {
  try {
    const r = await restartSteamService();
    if (r.ok) return;
    console.warn("[Ally Fix] service restart unavailable:", r.error);
  } catch (e) {
    console.warn("[Ally Fix] service restart failed:", e);
  }
  SteamClient.User.StartRestart(false);
}

export function steamCfgPresent(status: PluginStatus): boolean {
  return (status.fixes.gyro.details as { steam_cfg_present?: boolean }).steam_cfg_present === true;
}

/**
 * Whether the gyro fix ending up `enabledAfter` in `mode` changes Steam's steam_dev.cfg,
 * which Steam only reads at start-up. Compared against what is in the file now.
 */
export function gyroNeedsSteamRestart(status: PluginStatus, enabledAfter: boolean, mode: GyroMode): boolean {
  return (enabledAfter && mode === "complex") !== steamCfgPresent(status);
}

/** The native half of the layout fix lives in Steam's process: on ≠ loaded means a restart. */
export function layoutNeedsSteamRestart(status: PluginStatus, enabledAfter: boolean): boolean {
  const d = status.fixes.gamepad_layout?.details as Partial<GamepadLayoutDetails> | undefined;
  return enabledAfter !== (d?.shim_active === true);
}

export const RESTART_TEXT = "Steam reads this gyro setting only when it starts. Apply the change and restart Steam now?";
export const LAYOUT_RESTART_TEXT =
  "Steam builds the controller layout only when it starts. Apply the change and restart Steam now?";

/** Fixes whose toggle may need a Steam restart: when, and what to tell the user. */
export const RESTART_RULES: Partial<Record<FixId, { needs: (s: PluginStatus, enabledAfter: boolean) => boolean; text: string }>> = {
  gyro: { needs: (s, on) => gyroNeedsSteamRestart(s, on, s.options.gyro.mode), text: RESTART_TEXT },
  gamepad_layout: { needs: layoutNeedsSteamRestart, text: LAYOUT_RESTART_TEXT },
};

export type Choice = "ok" | "middle" | "cancel";

/** Yes/no (optionally three-way) dialog; resolves when the user picks. Esc/background = cancel. */
export function confirm(opts: {
  title: string;
  description: string;
  ok: string;
  cancel?: string;
  middle?: string;
}): Promise<Choice> {
  return new Promise((resolve) => {
    let done = false;
    const pick = (d: Choice) => {
      if (done) return;
      done = true;
      resolve(d);
    };
    showModal(
      <ConfirmModal
        strTitle={opts.title}
        strDescription={opts.description}
        strOKButtonText={opts.ok}
        strCancelButtonText={opts.cancel ?? "Cancel"}
        strMiddleButtonText={opts.middle}
        onOK={() => pick("ok")}
        onMiddleButton={opts.middle ? () => pick("middle") : undefined}
        onCancel={() => pick("cancel")}
      />,
    );
  });
}
