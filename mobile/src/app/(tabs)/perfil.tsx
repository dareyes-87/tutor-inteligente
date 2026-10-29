import { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { obtenerMiGrado, obtenerRacha, obtenerRanking } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Colors } from "@/lib/colors";

interface Datos {
  grado: string | null;
  mejorRacha: number;
  puntos: number;
}

export default function PerfilScreen() {
  const { user, logout } = useAuth();
  const [datos, setDatos] = useState<Datos | null>(null);
  const [cargando, setCargando] = useState(true);

  const cargar = useCallback(async () => {
    try {
      const [grado, racha, ranking] = await Promise.all([obtenerMiGrado(), obtenerRacha(), obtenerRanking()]);
      // /auth/me no trae los puntos: se toman de la propia fila del ranking del grado.
      const yo = ranking.ranking.find((r) => r.posicion === ranking.mi_posicion);
      setDatos({ grado: grado.nombre, mejorRacha: racha.mejor_racha, puntos: yo?.puntos_totales ?? 0 });
    } catch {
      setDatos(null);
    } finally {
      setCargando(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      cargar();
    }, [cargar]),
  );

  function confirmarSalida() {
    Alert.alert("Cerrar sesión", "¿Seguro que quieres salir?", [
      { text: "Cancelar", style: "cancel" },
      { text: "Cerrar sesión", style: "destructive", onPress: () => logout() },
    ]);
  }

  const iniciales = `${user?.nombre?.[0] ?? ""}${user?.apellido?.[0] ?? ""}`;

  return (
    <SafeAreaView style={styles.root} edges={["top"]}>
      <ScrollView
        contentContainerStyle={{ padding: 20, paddingBottom: 32 }}
        refreshControl={<RefreshControl refreshing={false} onRefresh={cargar} tintColor={Colors.orange} />}
      >
        <Text style={styles.titulo}>Mi perfil 👤</Text>

        <View style={styles.card}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{iniciales}</Text>
          </View>
          <Text style={styles.nombre}>
            {user?.nombre} {user?.apellido}
          </Text>
          <Text style={styles.usuario}>@{user?.username}</Text>
          {cargando ? (
            <ActivityIndicator color={Colors.orange} style={{ marginTop: 12 }} />
          ) : (
            !!datos?.grado && (
              <View style={styles.gradoBadge}>
                <Text style={styles.gradoText}>🎒 {datos.grado}</Text>
              </View>
            )
          )}
        </View>

        <View style={styles.stats}>
          <View style={styles.stat}>
            <Text style={styles.statNum}>🏆 {datos?.mejorRacha ?? "–"}</Text>
            <Text style={styles.statLabel}>Mejor racha (días)</Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statNum}>⭐ {datos?.puntos ?? "–"}</Text>
            <Text style={styles.statLabel}>Puntos</Text>
          </View>
        </View>

        <Pressable
          onPress={confirmarSalida}
          style={({ pressed }) => [styles.salir, { transform: [{ translateY: pressed ? 2 : 0 }] }]}
        >
          <Text style={styles.salirText}>Cerrar sesión</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.cream },
  titulo: { fontSize: 24, fontWeight: "900", color: Colors.navy, marginBottom: 12 },
  card: { backgroundColor: Colors.white, borderRadius: 20, padding: 24, alignItems: "center", borderWidth: 1, borderColor: Colors.border },
  avatar: { width: 76, height: 76, borderRadius: 38, backgroundColor: Colors.orange, alignItems: "center", justifyContent: "center", marginBottom: 12 },
  avatarText: { color: Colors.white, fontWeight: "900", fontSize: 28 },
  nombre: { fontSize: 20, fontWeight: "900", color: Colors.navy, textAlign: "center" },
  usuario: { fontSize: 14, fontWeight: "700", color: Colors.textLight, marginTop: 4 },
  gradoBadge: { backgroundColor: "#FFF1E7", borderRadius: 999, paddingHorizontal: 14, paddingVertical: 6, marginTop: 12 },
  gradoText: { color: Colors.orangeDark, fontWeight: "800", fontSize: 13.5 },
  stats: { flexDirection: "row", gap: 12, marginTop: 14 },
  stat: { flex: 1, backgroundColor: Colors.white, borderRadius: 18, paddingVertical: 18, alignItems: "center", borderWidth: 1, borderColor: Colors.border },
  statNum: { fontSize: 22, fontWeight: "900", color: Colors.navy },
  statLabel: { fontSize: 12.5, fontWeight: "800", color: Colors.textLight, marginTop: 4 },
  salir: { backgroundColor: Colors.red, borderRadius: 16, paddingVertical: 15, alignItems: "center", marginTop: 24 },
  salirText: { color: Colors.white, fontWeight: "900", fontSize: 16 },
});
