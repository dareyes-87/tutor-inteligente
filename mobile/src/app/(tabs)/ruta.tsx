import { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
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
  obtenerMisLibros,
  obtenerRacha,
  obtenerRanking,
  obtenerRuta,
  type LibroDisponible,
  type RutaAprendizaje,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Colors } from "@/lib/colors";

export default function MiRutaScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [libros, setLibros] = useState<LibroDisponible[]>([]);
  const [libroIdSeleccionado, setLibroIdSeleccionado] = useState<number | null>(null);
  const [ruta, setRuta] = useState<RutaAprendizaje | null>(null);
  const [racha, setRacha] = useState(0);
  const [puntos, setPuntos] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [cambiando, setCambiando] = useState(false); // cambio de pestaña de asignatura
  const [error, setError] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  // Recuerda la última asignatura elegida para no perderla al recargar al enfocar.
  const seleccionRef = useRef<number | null>(null);

  const cargar = useCallback(async () => {
    try {
      const [librosResp, rachaResp, rankingResp] = await Promise.all([
        obtenerMisLibros(),
        obtenerRacha(),
        obtenerRanking(),
      ]);
      setLibros(librosResp);
      setRacha(rachaResp.racha_actual);
      const yo = rankingResp.ranking.find((e) => e.posicion === rankingResp.mi_posicion);
      setPuntos(yo?.puntos_totales ?? 0);
      if (librosResp.length === 0) {
        setRuta(null);
        setLibroIdSeleccionado(null);
        setError(false);
        return;
      }
      const preferido = seleccionRef.current;
      const activo =
        preferido != null && librosResp.some((lb) => lb.libro_id === preferido)
          ? preferido
          : librosResp[0].libro_id;
      seleccionRef.current = activo;
      setLibroIdSeleccionado(activo);
      const r = await obtenerRuta(activo);
      setRuta(r);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setCargando(false);
      setCambiando(false);
    }
  }, []);

  // Recarga al enfocar la pantalla (vuelves de estudiar/practicar).
  useFocusEffect(
    useCallback(() => {
      cargar();
    }, [cargar]),
  );

  // Cambiar de asignatura: muestra un estado sutil sin recargar toda la pantalla.
  function seleccionarAsignatura(libroId: number) {
    if (libroId === libroIdSeleccionado || cambiando) return;
    seleccionRef.current = libroId;
    setCambiando(true);
    setLibroIdSeleccionado(libroId);
    obtenerRuta(libroId)
      .then((r) => {
        setRuta(r);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setCambiando(false));
  }

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

  // Sin libros disponibles para el grado (aún no se han subido/indexado).
  if (libros.length === 0) {
    return (
      <SafeAreaView style={styles.centro} edges={["top"]}>
        <Text style={{ fontSize: 44 }}>🐯</Text>
        <Text style={styles.errorText}>Aún no hay libros disponibles para tu grado.</Text>
      </SafeAreaView>
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
        {/* Selector de asignatura (solo si el grado tiene más de un libro) */}
        {libros.length > 1 && (
          <SafeAreaView edges={["top"]} style={{ backgroundColor: Colors.navy }}>
            <View style={styles.asigRow}>
              {libros.map((lb) => {
                const activa = lb.libro_id === libroIdSeleccionado;
                return (
                  <Pressable
                    key={lb.libro_id}
                    onPress={() => seleccionarAsignatura(lb.libro_id)}
                    disabled={cambiando}
                    style={[styles.asigChip, activa && styles.asigChipActiva, cambiando && { opacity: 0.6 }]}
                  >
                    <Text style={[styles.asigChipText, activa && styles.asigChipTextActiva]}>
                      📚 {lb.asignatura_nombre}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </SafeAreaView>
        )}

        <View style={{ opacity: cambiando ? 0.5 : 1 }}>
          {/* Header con gradiente */}
          <LinearGradient colors={[Colors.navy, Colors.navyLight]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}>
            <SafeAreaView edges={libros.length > 1 ? [] : ["top"]}>
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
  asigRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 4,
  },
  asigChip: {
    borderRadius: 12,
    borderWidth: 2,
    borderColor: "rgba(255,255,255,0.18)",
    backgroundColor: "rgba(255,255,255,0.08)",
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  asigChipActiva: { borderColor: Colors.orange, backgroundColor: "rgba(249,115,22,0.22)" },
  asigChipText: { color: "#CBD5E1", fontSize: 13, fontWeight: "800" },
  asigChipTextActiva: { color: Colors.orange },
});
