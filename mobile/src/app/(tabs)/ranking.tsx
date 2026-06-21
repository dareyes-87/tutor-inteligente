import { useCallback, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { obtenerRanking, type RankingResponse } from "@/lib/api";
import { Colors } from "@/lib/colors";

const AVATAR = ["#F59E0B", "#2563EB", "#F97316", "#8B5CF6", "#EC4899", "#22C55E", "#06B6D4", "#EF4444"];
const MEDALLA: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

export default function RankingScreen() {
  const [data, setData] = useState<RankingResponse | null>(null);
  const [cargando, setCargando] = useState(true);

  const cargar = useCallback(async () => {
    try {
      setData(await obtenerRanking());
    } catch {
      setData({ ranking: [], mi_posicion: 0 });
    } finally {
      setCargando(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      cargar();
    }, [cargar]),
  );

  return (
    <SafeAreaView style={styles.root} edges={["top"]}>
      <ScrollView
        contentContainerStyle={{ padding: 20, paddingBottom: 32 }}
        refreshControl={<RefreshControl refreshing={false} onRefresh={cargar} tintColor={Colors.orange} />}
      >
        <Text style={styles.titulo}>Tabla de posiciones 🏆</Text>

        {cargando ? (
          <ActivityIndicator color={Colors.orange} size="large" style={{ marginTop: 40 }} />
        ) : !data || data.ranking.length === 0 ? (
          <View style={styles.vacio}>
            <Text style={styles.vacioTitulo}>Aún no hay posiciones</Text>
            <Text style={styles.vacioSub}>Completa lecciones y gana puntos para aparecer aquí.</Text>
          </View>
        ) : (
          <View style={{ gap: 10, marginTop: 8 }}>
            {data.ranking.map((r) => {
              const yo = r.posicion === data.mi_posicion;
              return (
                <View key={r.posicion} style={[styles.fila, yo && styles.filaYo]}>
                  <Text style={styles.pos}>{MEDALLA[r.posicion] ?? r.posicion}</Text>
                  <View style={[styles.avatar, { backgroundColor: AVATAR[(r.posicion - 1) % AVATAR.length] }]}>
                    <Text style={styles.avatarText}>
                      {r.nombre[0]}
                      {r.apellido[0]}
                    </Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={styles.nombreRow}>
                      <Text style={styles.nombre}>
                        {r.nombre} {r.apellido}
                      </Text>
                      {yo && (
                        <View style={styles.tuBadge}>
                          <Text style={styles.tuText}>Tú</Text>
                        </View>
                      )}
                    </View>
                    <Text style={styles.meta}>
                      {r.lecciones_completadas} {r.lecciones_completadas === 1 ? "lección" : "lecciones"} · 🔥 {r.racha_actual}
                    </Text>
                  </View>
                  <Text style={styles.pts}>{r.puntos_totales}</Text>
                </View>
              );
            })}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.cream },
  titulo: { fontSize: 24, fontWeight: "900", color: Colors.navy, marginBottom: 8 },
  fila: { flexDirection: "row", alignItems: "center", gap: 14, backgroundColor: Colors.white, borderRadius: 16, paddingHorizontal: 16, paddingVertical: 13, borderWidth: 1, borderColor: Colors.border },
  filaYo: { backgroundColor: "#FFF1E7", borderColor: Colors.orange },
  pos: { width: 30, textAlign: "center", fontSize: 16, fontWeight: "900", color: Colors.textLight },
  avatar: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" },
  avatarText: { color: Colors.white, fontWeight: "900", fontSize: 15 },
  nombreRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  nombre: { fontSize: 15.5, fontWeight: "800", color: Colors.navy },
  tuBadge: { backgroundColor: Colors.orange, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
  tuText: { color: Colors.white, fontSize: 11, fontWeight: "800" },
  meta: { fontSize: 12, fontWeight: "700", color: Colors.textLight, marginTop: 2 },
  pts: { fontSize: 16, fontWeight: "900", color: Colors.navy },
  vacio: { backgroundColor: Colors.white, borderRadius: 20, padding: 32, alignItems: "center", marginTop: 30, borderWidth: 1, borderColor: Colors.border },
  vacioTitulo: { fontSize: 17, fontWeight: "900", color: Colors.navy },
  vacioSub: { fontSize: 13.5, fontWeight: "700", color: Colors.textLight, textAlign: "center", marginTop: 6 },
});
