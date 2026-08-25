import { ConfirmModal, showModal } from "@decky/ui";
import type { GyroMode, PluginStatus } from "./types";

export function restartSteam() {
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

export const RESTART_TEXT = "Steam reads this gyro setting only when it starts. Apply the change and restart Steam now?";
