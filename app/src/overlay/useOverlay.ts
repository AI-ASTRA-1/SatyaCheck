/**
 * useOverlay: drives the native OverlayService in response to socket state.
 *
 * Rules:
 *   - showOverlay() on every RiskUpdate, passing score/risk_level/verdict as-is.
 *   - hideOverlay() when socket is disconnected, connecting, or ended.
 *   - The overlay is display-only; it never acts on the call.
 */

import { useEffect } from "react";
import {
  hideOverlay,
  isPermissionGranted,
  requestPermission,
  showOverlay,
} from "../../modules/overlay";
import { SocketStatus } from "../ws/useRiskSocket";

export function useOverlay(state: SocketStatus) {
  useEffect(() => {
    if (state.status === "live") {
      const { score, risk_level, verdict } = state.latest;
      showOverlay(score, risk_level, verdict);
    } else {
      // disconnected / connecting / session / ended -> hide so no stale score
      hideOverlay();
    }
  }, [state]);
}

export { isPermissionGranted, requestPermission };
