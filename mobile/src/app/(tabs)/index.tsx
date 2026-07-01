import { useCallback, useState } from "react";
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

import { ProgressBar } from "@/components/ProgressBar";
import {
  getPerfil,
  obtenerMiLibro,
  obtenerRacha,
  obtenerRuta,
  type PerfilTema,
  type RachaResponse,
  type RutaAprendizaje,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Colors } from "@/lib/colors";

/** Progreso agregado por asignatura (promedio ponderado por nº de actividades). */
type AsignaturaProgreso = { asignatura: string; avance: number; actividades: number };

function agruparPorAsignatura(perfil: PerfilTema[]): AsignaturaProgreso[] {
  const mapa = new Map<string, { suma: number; total: number }>();
  for (const p of perfil) {
    const cur = mapa.get(p.asignatura) ?? { suma: 0, total: 0 };
    cur.suma += p.puntaje_promedio * p.total_actividades;
    cur.total += p.total_actividades;
    mapa.set(p.asignatura, cur);
  }
  return [...mapa.entries()].map(([asignatura, { suma, total }]) => ({
    asignatura,
    avance: total === 0 ? 0 : Math.round(suma / total),
    actividades: total,
  }));
}

export default function InicioScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [ruta, setRuta] = useState<RutaAprendizaje | null>(null);
  const [racha, setRacha] = useState<RachaResponse | null>(null);
  const [asignaturas, setAsignaturas] = useState<AsignaturaProgreso[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [rachaResp, rutaResp, perfilResp] = await Promise.all([
        obtenerRacha(),
        obtenerMiLibro().then((mi) => obtenerRuta(mi.libro_id)),
        getPerfil(),
      ]);
      setRacha(rachaResp);
      setRuta(rutaResp);
      setAsignaturas(agruparPorAsignatura(perfilResp));
      setError(false);
    } catch {
      setError(true);
    } finally {
      setCargando(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      cargar();
    }, [cargar]),
  );

  if (cargando) {
    return (
      <View style={styles.centro}>
        <ActivityIndicator color={Colors.orange} size="large" />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centro}>
        <Text style={styles.errorText}>No se pudo cargar tu inicio.</Text>
      </View>
    );
  }

  const leccionActual = ruta
    ? Math.min(ruta.total_lecciones, ruta.lecciones_completadas + 1)
    : 0;

  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream }}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: 32 }}
        refreshControl={
          <RefreshControl refreshing={false} onRefresh={cargar} tintColor={Colors.orange} />
        }
      >
        {/* Saludo */}
        <LinearGradient
          colors={[Colors.navy, Colors.navyLight]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
        >
          <SafeAreaView edges={["top"]}>
            <View style={styles.header}>
              <Text style={styles.hola}>¡Hola, {user?.nombre ?? "estudiante"}! 🐯</Text>
              <Text style={styles.sub}>¿Seguimos aprendiendo hoy?</Text>
            </View>
          </SafeAreaView>
        </LinearGradient>

        <View style={styles.body}>
          {/* Racha */}
          <View style={styles.rachaCard}>
            <Text style={styles.rachaEmoji}>🔥</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.rachaNum}>
                {racha?.racha_actual ?? 0}{" "}
                {racha?.racha_actual === 1 ? "día" : "días"}
              </Text>
              <Text style={styles.rachaSub}>
                {racha?.activo_hoy ? "¡Ya practicaste hoy! 🎉" : "¡No rompas la racha!"}
              </Text>
              <View style={styles.rachaBadge}>
                <Text style={styles.rachaBadgeText}>🏆 Mejor racha: {racha?.mejor_racha ?? 0}</Text>
              </View>
            </View>
          </View>

          {/* Mi ruta */}
          <View style={styles.card}>
            <View style={styles.cardHead}>
              <Text style={styles.cardTitulo}>🗺️ Mi ruta</Text>
              <Pressable onPress={() => router.push("/ruta")} hitSlop={8}>
                <Text style={styles.continuar}>Continuar →</Text>
              </Pressable>
            </View>
            {ruta ? (
              <>
                <Text style={styles.rutaLinea}>
                  Vas en la{" "}
                  <Text style={{ color: Colors.orange, fontWeight: "900" }}>
                    Lección {leccionActual} de {ruta.total_lecciones}
                  </Text>{" "}
                  · {ruta.asignatura}
                </Text>
                <ProgressBar progress={ruta.progreso_porcentaje} height={12} />
                <View style={styles.rutaFoot}>
                  <Text style={styles.rutaFootText}>
                    {ruta.lecciones_completadas} de {ruta.total_lecciones} completadas
                  </Text>
                  <Text style={styles.rutaPct}>{Math.round(ruta.progreso_porcentaje)}%</Text>
                </View>
              </>
            ) : (
              <Text style={styles.vacioText}>Cargando tu progreso…</Text>
            )}
          </View>

          {/* Mis asignaturas */}
          <Text style={styles.seccionTitulo}>Mis asignaturas</Text>
          {asignaturas.length > 0 ? (
            asignaturas.map((a) => (
              <View key={a.asignatura} style={styles.asigCard}>
                <View style={styles.asigHead}>
                  <Text style={styles.asigNombre}>📚 {a.asignatura}</Text>
                  <Text style={styles.asigPct}>{a.avance}%</Text>
                </View>
                <ProgressBar progress={a.avance} color={Colors.green} height={10} />
                <Text style={styles.asigMeta}>
                  {a.actividades} {a.actividades === 1 ? "actividad" : "actividades"} completadas
                </Text>
              </View>
            ))
          ) : (
            <View style={styles.vacioCard}>
              <Text style={styles.vacioEmoji}>📚</Text>
              <Text style={styles.vacioTitulo}>Aún no has practicado</Text>
              <Text style={styles.vacioSub}>
                Resuelve actividades y aquí verás tu avance por asignatura. 🌟
              </Text>
            </View>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  centro: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: Colors.cream },
  errorText: { fontSize: 15, fontWeight: "700", color: Colors.textLight },

  header: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 24 },
  hola: { fontSize: 24, fontWeight: "900", color: Colors.white },
  sub: { fontSize: 14, fontWeight: "700", color: "#CBD5E1", marginTop: 4 },

  body: { paddingHorizontal: 20, paddingTop: 18, gap: 16 },

  rachaCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 16,
    backgroundColor: "#FB923C",
    borderRadius: 22,
    paddingHorizontal: 20,
    paddingVertical: 18,
  },
  rachaEmoji: { fontSize: 44 },
  rachaNum: { fontSize: 26, fontWeight: "900", color: Colors.white },
  rachaSub: { fontSize: 13.5, fontWeight: "800", color: "rgba(255,255,255,0.95)", marginTop: 2 },
  rachaBadge: {
    alignSelf: "flex-start",
    marginTop: 10,
    backgroundColor: "rgba(255,255,255,0.22)",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 5,
  },
  rachaBadgeText: { fontSize: 12.5, fontWeight: "800", color: Colors.white },

  card: {
    backgroundColor: Colors.white,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: 20,
    gap: 12,
  },
  cardHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  cardTitulo: { fontSize: 16, fontWeight: "900", color: Colors.navy },
  continuar: { fontSize: 13, fontWeight: "800", color: Colors.blue },
  rutaLinea: { fontSize: 14, fontWeight: "700", color: Colors.textLight, lineHeight: 20 },
  rutaFoot: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  rutaFootText: { fontSize: 12.5, fontWeight: "800", color: Colors.textLight },
  rutaPct: { fontSize: 13, fontWeight: "900", color: Colors.orange },
  vacioText: { fontSize: 14, fontWeight: "700", color: Colors.textLight },

  seccionTitulo: { fontSize: 18, fontWeight: "900", color: Colors.navy, marginTop: 4 },
  asigCard: {
    backgroundColor: Colors.white,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: 18,
    gap: 10,
  },
  asigHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  asigNombre: { fontSize: 15, fontWeight: "900", color: Colors.navy },
  asigPct: { fontSize: 15, fontWeight: "900", color: Colors.green },
  asigMeta: { fontSize: 12.5, fontWeight: "700", color: Colors.textLight },

  vacioCard: {
    backgroundColor: Colors.white,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: 28,
    alignItems: "center",
    gap: 6,
  },
  vacioEmoji: { fontSize: 40, marginBottom: 2 },
  vacioTitulo: { fontSize: 16, fontWeight: "900", color: Colors.navy },
  vacioSub: { fontSize: 13.5, fontWeight: "700", color: Colors.textLight, textAlign: "center", lineHeight: 20 },
});
