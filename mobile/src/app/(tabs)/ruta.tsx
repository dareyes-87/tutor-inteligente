import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { LeccionCard } from "@/components/LeccionCard";
import { ProgressBar } from "@/components/ProgressBar";
import {
  iniciarLeccion,
  obtenerMiLibro,
  obtenerRacha,
  obtenerRanking,
  obtenerRuta,
  type RutaAprendizaje,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Colors } from "@/lib/colors";

export default function MiRutaScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [ruta, setRuta] = useState<RutaAprendizaje | null>(null);
  const [racha, setRacha] = useState(0);
  const [puntos, setPuntos] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [r, rachaResp, rankingResp] = await Promise.all([
        obtenerMiLibro().then((mi) => obtenerRuta(mi.libro_id)),
        obtenerRacha(),
        obtenerRanking(),
      ]);
      setRuta(r);
      setRacha(rachaResp.racha_actual);
      const yo = rankingResp.ranking.find((e) => e.posicion === rankingResp.mi_posicion);
      setPuntos(yo?.puntos_totales ?? 0);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setCargando(false);
    }
  }, []);

  // Recarga al enfocar la pantalla (vuelves de estudiar/practicar).
  useFocusEffect(
    useCallback(() => {
      cargar();
    }, [cargar]),
  );

  async function empezar(id: number) {
    if (ocupado) return;
    setOcupado(true);
    try {
      await iniciarLeccion(id);
      await cargar();
    } catch {
      /* noop */
    } finally {
      setOcupado(false);
    }
  }

  const estudiar = (id: number) =>
    router.push({ pathname: "/leccion/[id]/estudiar", params: { id: String(id) } });
  const practicar = (id: number) =>
    router.push({ pathname: "/leccion/[id]/practicar", params: { id: String(id) } });

  if (cargando) {
    return (
      <View style={styles.centro}>
        <ActivityIndicator color={Colors.orange} size="large" />
      </View>
    );
  }

  if (error || !ruta) {
    return (
      <View style={styles.centro}>
        <Text style={styles.errorText}>No se pudo cargar tu ruta.</Text>
      </View>
    );
  }

  const leccionActual = Math.min(ruta.total_lecciones, ruta.lecciones_completadas + 1);

  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream }}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: 32 }}
        refreshControl={<RefreshControl refreshing={false} onRefresh={cargar} tintColor={Colors.orange} />}
      >
        {/* Header con gradiente */}
        <LinearGradient colors={[Colors.navy, Colors.navyLight]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}>
          <SafeAreaView edges={["top"]}>
            <View style={styles.header}>
              <View style={styles.headerTop}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.hola}>¡Hola, {user?.nombre ?? "estudiante"}! 🐯</Text>
                  <Text style={styles.leccionN}>
                    Lección {leccionActual} de {ruta.total_lecciones}
                  </Text>
                  <Text style={styles.asignatura}>{ruta.asignatura}</Text>
                </View>
                <View style={styles.pills}>
                  <View style={styles.pill}>
                    <Text style={styles.pillIcon}>⭐</Text>
                    <Text style={styles.pillVal}>{puntos}</Text>
                  </View>
                  <View style={styles.pill}>
                    <Text style={styles.pillIcon}>🔥</Text>
                    <Text style={styles.pillVal}>{racha}</Text>
                  </View>
                </View>
              </View>
              <View style={styles.progressRow}>
                <View style={{ flex: 1 }}>
                  <ProgressBar progress={ruta.progreso_porcentaje} color={Colors.orange} trackColor="rgba(255,255,255,0.15)" height={12} />
                </View>
                <Text style={styles.progressPct}>{Math.round(ruta.progreso_porcentaje)}%</Text>
              </View>
            </View>
          </SafeAreaView>
        </LinearGradient>

        {/* Lista de lecciones */}
        <View style={styles.lista}>
          <Text style={styles.listaTitulo}>Tu ruta de aprendizaje</Text>
          {ruta.lecciones.map((l) => (
            <LeccionCard
              key={l.id}
              leccion={l}
              onEmpezar={empezar}
              onEstudiar={estudiar}
              onPracticar={practicar}
              ocupado={ocupado}
            />
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  centro: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: Colors.cream },
  errorText: { fontSize: 15, fontWeight: "700", color: Colors.textLight },
  header: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 22 },
  headerTop: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  hola: { fontSize: 14, fontWeight: "800", color: "#FED7AA" },
  leccionN: { fontSize: 26, fontWeight: "900", color: Colors.white, marginTop: 4 },
  asignatura: { fontSize: 14, fontWeight: "700", color: "#CBD5E1", marginTop: 3 },
  pills: { gap: 8 },
  pill: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "rgba(255,255,255,0.12)", borderRadius: 13, paddingHorizontal: 12, paddingVertical: 7 },
  pillIcon: { fontSize: 16 },
  pillVal: { fontSize: 16, fontWeight: "900", color: Colors.white },
  progressRow: { flexDirection: "row", alignItems: "center", gap: 12, marginTop: 16 },
  progressPct: { fontSize: 15, fontWeight: "900", color: Colors.orange },
  lista: { paddingHorizontal: 20, paddingTop: 22 },
  listaTitulo: { fontSize: 18, fontWeight: "900", color: Colors.navy, marginBottom: 14 },
});
