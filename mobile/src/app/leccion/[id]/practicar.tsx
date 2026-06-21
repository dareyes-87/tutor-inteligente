import { StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";

import { Colors } from "@/lib/colors";

export default function PracticarPlaceholder() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return (
    <View style={styles.root}>
      <Text style={styles.emoji}>🎯</Text>
      <Text style={styles.titulo}>Practicar</Text>
      <Text style={styles.sub}>Lección #{id}</Text>
      <Text style={styles.proximamente}>Próximamente (Parte 2)</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.cream, alignItems: "center", justifyContent: "center", gap: 6 },
  emoji: { fontSize: 64 },
  titulo: { fontSize: 24, fontWeight: "900", color: Colors.navy },
  sub: { fontSize: 15, fontWeight: "700", color: Colors.textLight },
  proximamente: { marginTop: 12, fontSize: 14, fontWeight: "800", color: Colors.orange },
});
