import { View } from "react-native";

import { Colors } from "@/lib/colors";

export function ProgressBar({
  progress,
  color = Colors.orange,
  trackColor = "#ECE7DE",
  height = 10,
}: {
  progress: number; // 0-100
  color?: string;
  trackColor?: string;
  height?: number;
}) {
  const pct = Math.max(0, Math.min(100, progress));
  return (
    <View style={{ height, borderRadius: 999, backgroundColor: trackColor, overflow: "hidden" }}>
      <View style={{ width: `${pct}%`, height: "100%", borderRadius: 999, backgroundColor: color }} />
    </View>
  );
}
