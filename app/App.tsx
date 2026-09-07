import React, { useCallback, useEffect, useState } from "react";
import { Alert, Platform } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { isPermissionGranted, requestPermission } from "./src/overlay/useOverlay";
import { AlertHistoryScreen } from "./src/screens/AlertHistoryScreen";
import { OverlayScreen } from "./src/screens/OverlayScreen";
import { WS_URL } from "./src/config";
import { useRiskSocket } from "./src/ws/useRiskSocket";

type Screen = "main" | "history";

export default function App() {
  const [screen, setScreen] = useState<Screen>("main");
  const { state, alertHistory, reconnect } = useRiskSocket(WS_URL);

  // Request SYSTEM_ALERT_WINDOW on first launch (Android only).
  useEffect(() => {
    if (Platform.OS !== "android") return;

    const checkPermission = async () => {
      try {
        const granted = isPermissionGranted();
        if (!granted) {
          Alert.alert(
            "Overlay permission needed",
            'SATYACHECK needs the "Draw over other apps" permission to show warnings during calls. Tap OK to open settings.',
            [
              { text: "Cancel", style: "cancel" },
              {
                text: "Open settings",
                onPress: () => requestPermission(),
              },
            ]
          );
        }
      } catch {
        // Native module not available (e.g., running on iOS or in Expo Go).
      }
    };

    checkPermission();
  }, []);

  const goHistory = useCallback(() => setScreen("history"), []);
  const goMain = useCallback(() => setScreen("main"), []);

  return (
    <SafeAreaProvider>
      {screen === "main" ? (
        <OverlayScreen
          state={state}
          onReconnect={reconnect}
          onHistory={goHistory}
        />
      ) : (
        <AlertHistoryScreen history={alertHistory} onBack={goMain} />
      )}
    </SafeAreaProvider>
  );
}
