import { useCallback, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { ProgressBar } from "@/components/ProgressBar";
import { getPerfil, type PerfilTema } from "@/lib/api";
import { Colors } from "@/lib/colors";

const NIVEL: Record<string, { color: string; label: string }> = {
  domina: { color: Colors.green, label: "Domina" },
  en_proceso: { color: "#F59E0B", label: "En proceso" },
  refuerzo: { color: Colors.red, label: "Refuerzo" },
};

export default function ProgresoScreen() {
  const [perfil, setPerfil] = useState<PerfilTema[] | null>(null);
  const [cargando, setCargando] = useState(true);

  const cargar = useCallback(async () => {
    try {
      setPerfil(await getPerfil());
    } catch {
      setPerfil([]);
    } finally {
      setCargando(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      cargar();
    }, [cargar]),
  );

  const items = perfil ?? [];
  const totalAct = items.reduce((s, p) => s + p.total_actividades, 0);
  const avance = items.length ? Math.round(items.reduce((s, p) => s + p.puntaje_promedio, 0) / items.length) : 0;

  return (
    <SafeAreaView style={styles.root} edges={["top"]}>
      <ScrollView
        contentContainerStyle={{ padding: 20, paddingBottom: 32 }}
        refreshControl={<RefreshControl refreshing={false} onRefresh={cargar} tintColor={Colors.orange} />}
      >
        <Text style={styles.titulo}>Mi progreso</Text>
        <Text style={styles.subtitulo}>Tu comprensión tema por tema</Text>

        {cargando ? (
          <ActivityIndicator color={Colors.orange} size="large" style={{ marginTop: 40 }} />
        ) : items.length === 0 ? (
          <View style={styles.vacio}>
            <Text style={styles.vacioTitulo}>Aún no has completado actividades</Text>
            <Text style={styles.vacioSub}>¡Empieza a practicar para ver tu progreso aquí!</Text>
          </View>
        ) : (
          <>
            <View style={styles.statsRow}>
              <View style={styles.statCard}>
                <Text style={[styles.statVal, { color: Colors.green }]}>{totalAct}</Text>
                <Text style={styles.statLabel}>ACTIVIDADES</Text>
              </View>
              <View style={styles.statCard}>
                <Text style={[styles.statVal, { color: Colors.orange }]}>{avance}%</Text>
                <Text style={styles.statLabel}>AVANCE</Text>
              </View>
            </View>

            {items.map((p) => {
              const nv = NIVEL[p.nivel] ?? NIVEL.refuerzo;
              return (
                <View key={`${p.asignatura}-${p.tema}`} style={styles.card}>
                  <View style={styles.cardTop}>
                    <Text style={styles.tema} numberOfLines={1}>{p.tema}</Text>
                    <View style={[styles.chip, { backgroundColor: nv.color + "22" }]}>
                      <Text style={[styles.chipText, { color: nv.color }]}>{nv.label}</Text>
                    </View>
                  </View>
                  <View style={styles.barRow}>
                    <View style={{ flex: 1 }}>
                      <ProgressBar progress={p.puntaje_promedio} color={nv.color} />
                    </View>
                    <Text style={[styles.barVal, { color: nv.color }]}>{Math.round(p.puntaje_promedio)}</Text>
                  </View>
                  <Text style={styles.meta}>
                    {p.total_actividades} {p.total_actividades === 1 ? "actividad" : "actividades"} · {p.asignatura}
                  </Text>
                </View>
              );
            })}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.cream },
  titulo: { fontSize: 24, fontWeight: "900", color: Colors.navy },
  subtitulo: { fontSize: 14, fontWeight: "700", color: Colors.textLight, marginTop: 3, marginBottom: 18 },
  statsRow: { flexDirection: "row", gap: 12, marginBottom: 18 },
  statCard: { flex: 1, backgroundColor: Colors.white, borderRadius: 16, padding: 16, alignItems: "center", borderWidth: 1, borderColor: Colors.border },
  statVal: { fontSize: 26, fontWeight: "900" },
  statLabel: { fontSize: 10.5, fontWeight: "800", color: Colors.textLight, marginTop: 2 },
  card: { backgroundColor: Colors.white, borderRadius: 18, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: Colors.border },
  cardTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 10 },
  tema: { flex: 1, fontSize: 15.5, fontWeight: "800", color: Colors.navy, marginRight: 10 },
  chip: { borderRadius: 999, paddingHorizontal: 12, paddingVertical: 5 },
  chipText: { fontSize: 12, fontWeight: "800" },
  barRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  barVal: { fontSize: 14, fontWeight: "900", width: 32, textAlign: "right" },
  meta: { fontSize: 12, fontWeight: "700", color: Colors.textLight, marginTop: 8 },
  vacio: { backgroundColor: Colors.white, borderRadius: 20, padding: 32, alignItems: "center", marginTop: 30, borderWidth: 1, borderColor: Colors.border },
  vacioTitulo: { fontSize: 17, fontWeight: "900", color: Colors.navy, textAlign: "center" },
  vacioSub: { fontSize: 13.5, fontWeight: "700", color: Colors.textLight, textAlign: "center", marginTop: 6 },
});
