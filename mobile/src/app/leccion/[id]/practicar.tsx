import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Animated,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import {
  completarNivel,
  iniciarLeccion,
  obtenerMisLibros,
  obtenerRuta,
  responderActividad,
  type ActividadResponse,
  type CompletarNivelResponse,
  type LeccionEnRuta,
  type ResultadoResponse,
} from "@/lib/api";
import { Colors } from "@/lib/colors";
import {
  generarActividadesSesion,
  tomarActividadesPrecargadas,
} from "@/lib/preload-actividades";

type Fase = "cargando" | "error" | "ejercicio" | "resultado";

export default function PracticarScreen() {
  const { id, fragmentIds: fragmentIdsParam, nivel: nivelParam } = useLocalSearchParams<{
    id: string;
    fragmentIds?: string;
    nivel?: string;
  }>();
  const leccionId = Number(id);
  const nivel = Number(nivelParam) || 1;
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [fase, setFase] = useState<Fase>("cargando");
  const [acts, setActs] = useState<ActividadResponse[]>([]);
  const [idx, setIdx] = useState(0);
  const [seleccion, setSeleccion] = useState("");
  const [orden, setOrden] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<ResultadoResponse | null>(null);
  const [resultados, setResultados] = useState<ResultadoResponse[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [inicio, setInicio] = useState(0);
  const [duracion, setDuracion] = useState(0);
  const [resultadoNivel, setResultadoNivel] = useState<CompletarNivelResponse | null>(null);
  const [intento, setIntento] = useState(0);

  const panelAnim = useRef(new Animated.Value(0)).current;
  const starAnim = useRef(new Animated.Value(0)).current;

  // --- Carga: asegurar en_progreso + generar 5 actividades ---
  useEffect(() => {
    let activo = true;
    (async () => {
      try {
        // Resolver a qué libro/asignatura pertenece la lección (no asumir Ciencias):
        // se busca la lección en la ruta de cada libro disponible del grado.
        const libros = await obtenerMisLibros();
        let asignaturaId = 1; // fallback
        let leccion: LeccionEnRuta | undefined;
        for (const lb of libros) {
          const r = await obtenerRuta(lb.libro_id);
          const l = r.lecciones.find((x) => x.id === leccionId);
          if (l) {
            leccion = l;
            asignaturaId = lb.asignatura_id;
            break;
          }
        }
        if (!leccion) throw new Error("no encontrada");
        if (leccion.estado === "bloqueada") throw new Error("bloqueada");
        if (leccion.estado === "disponible") await iniciarLeccion(leccionId);
        const tema = leccion.tema_clave || leccion.nombre;
        // Reusar los fragmentos que vio la micro-lección (vienen por params).
        let fragmentIds: number[] = [];
        try {
          fragmentIds = fragmentIdsParam ? JSON.parse(fragmentIdsParam) : [];
        } catch {
          fragmentIds = [];
        }
        // Si el estudiante pasó por Estudiar, las actividades ya se están
        // generando (o están listas) en segundo plano: se consumen aquí. Si no
        // hay pre-carga (entró directo) o quedó vacía, se generan sobre la
        // marcha. La generación es SECUENCIAL para no repetir preguntas.
        const precargadas = tomarActividadesPrecargadas(leccionId, nivel);
        let generadas = precargadas
          ? await precargadas
          : await generarActividadesSesion({ leccionId, asignaturaId, tema, fragmentIds });
        if (!activo) return;
        if (generadas.length === 0 && precargadas) {
          generadas = await generarActividadesSesion({ leccionId, asignaturaId, tema, fragmentIds });
          if (!activo) return;
        }
        if (generadas.length === 0) {
          setFase("error");
          return;
        }
        setActs(generadas);
        setInicio(Date.now());
        setFase("ejercicio");
      } catch {
        if (activo) setFase("error");
      }
    })();
    return () => {
      activo = false;
    };
  }, [leccionId, intento]);

  // Animación del panel de feedback (sube desde abajo).
  useEffect(() => {
    if (feedback) {
      panelAnim.setValue(0);
      Animated.spring(panelAnim, { toValue: 1, useNativeDriver: true, friction: 8, tension: 60 }).start();
    }
  }, [feedback, panelAnim]);

  // Animación de estrellas en resultados (pulso en loop).
  useEffect(() => {
    if (fase === "resultado") {
      Animated.loop(
        Animated.sequence([
          Animated.timing(starAnim, { toValue: 1, duration: 700, useNativeDriver: true }),
          Animated.timing(starAnim, { toValue: 0, duration: 700, useNativeDriver: true }),
        ]),
      ).start();
    }
  }, [fase, starAnim]);

  const act = acts[idx];
  const contenido = (act?.contenido ?? {}) as Record<string, unknown>;
  const str = (k: string) => String(contenido[k] ?? "");

  function respuestaLista(): boolean {
    if (!act) return false;
    if (act.tipo === "ordenar") {
      const total = ((contenido.elementos_desordenados as string[]) ?? []).length;
      return orden.length === total && total > 0;
    }
    return seleccion.trim() !== "";
  }

  function buildRespuesta(): Record<string, unknown> {
    if (act.tipo === "verdadero_falso") return { respuesta: seleccion === "true" };
    if (act.tipo === "ordenar") return { orden };
    return { respuesta: seleccion };
  }

  async function confirmar() {
    if (!act || !respuestaLista() || enviando) return;
    setEnviando(true);
    try {
      const res = await responderActividad(act.id, buildRespuesta());
      setResultados((prev) => [...prev, res]);
      setFeedback(res);
    } catch {
      Alert.alert("Error", "No se pudo enviar tu respuesta. Intenta de nuevo.");
    } finally {
      setEnviando(false);
    }
  }

  async function continuar() {
    setFeedback(null);
    setSeleccion("");
    setOrden([]);
    if (idx < acts.length - 1) {
      setIdx(idx + 1);
      return;
    }
    setDuracion(Math.round((Date.now() - inicio) / 1000));
    const aprobadas = resultados.filter((r) => r.puntaje >= 70).length;
    const ultimoPuntaje = resultados.length ? resultados[resultados.length - 1].puntaje : 0;
    try {
      // total real de la sesión: el umbral de aprobación es proporcional (no fijo).
      const res = await completarNivel(leccionId, ultimoPuntaje, nivel, aprobadas, acts.length);
      setResultadoNivel(res);
    } catch {
      /* el resumen se muestra igual sin avance de nivel */
    }
    setFase("resultado");
  }

  function abandonar() {
    Alert.alert("Salir de la práctica", "¿Seguro? Perderás el avance de esta práctica.", [
      { text: "Cancelar", style: "cancel" },
      { text: "Salir", style: "destructive", onPress: () => router.dismissAll() },
    ]);
  }

  // ---------------- Cargando ----------------
  if (fase === "cargando") {
    return (
      <View style={styles.centro}>
        <StatusBar style="light" />
        <Text style={styles.bigEmoji}>🐯</Text>
        <Text style={styles.cargandoTitulo}>Preparando tu práctica…</Text>
        <ActivityIndicator color={Colors.orange} size="large" style={{ marginTop: 16 }} />
      </View>
    );
  }

  // ---------------- Error ----------------
  if (fase === "error") {
    return (
      <View style={styles.centro}>
        <StatusBar style="light" />
        <Text style={styles.bigEmoji}>😕</Text>
        <Text style={styles.cargandoTitulo}>No se pudo preparar la práctica</Text>
        <View style={{ flexDirection: "row", gap: 12, marginTop: 20 }}>
          <Pressable
            onPress={() => {
              setFase("cargando");
              setIntento((n) => n + 1);
            }}
            style={[styles.botonGrande, { backgroundColor: Colors.orange }]}
          >
            <Text style={styles.botonGrandeText}>Reintentar</Text>
          </Pressable>
          <Pressable onPress={() => router.dismissAll()} style={[styles.botonGrande, { backgroundColor: "rgba(255,255,255,0.15)" }]}>
            <Text style={styles.botonGrandeText}>Volver</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  // ---------------- Resultados ----------------
  if (fase === "resultado") {
    const total = resultados.length;
    const aciertos = resultados.filter((r) => r.puntaje >= 70).length;
    const promedio = total ? Math.round(resultados.reduce((s, r) => s + r.puntaje, 0) / total) : 0;
    const tiempo = `${Math.floor(duracion / 60)}:${String(duracion % 60).padStart(2, "0")}`;
    const scale = starAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 1.25] });
    const aprobado = resultadoNivel?.aprobado ?? false;
    const domino = aprobado && resultadoNivel?.nivel_completado === 3;
    const titulo = domino
      ? "¡Lección Dominada! 👑"
      : aprobado
        ? `¡Nivel ${nivel} completado! 🎉`
        : "¡Sigue intentando! 💪";
    const irEstudiar = () =>
      router.replace({ pathname: "/leccion/[id]/estudiar", params: { id: String(leccionId) } });
    return (
      <View style={[styles.centro, { paddingHorizontal: 28 }]}>
        <StatusBar style="light" />
        <Animated.Text style={[styles.starsRow, { transform: [{ scale }] }]}>
          {domino ? "👑 ⭐⭐⭐" : "⭐ 🎉 ⭐"}
        </Animated.Text>
        <Text style={styles.resultTitulo}>{titulo}</Text>
        {!!resultadoNivel?.mensaje_feedback && (
          <Text style={styles.resultMensaje}>{resultadoNivel.mensaje_feedback}</Text>
        )}

        {aprobado && (resultadoNivel?.puntos_ganados ?? 0) > 0 && (
          <View style={{ alignItems: "center", gap: 6, marginBottom: 4 }}>
            <View style={styles.puntosBadge}>
              <Text style={styles.puntosBadgeText}>+{resultadoNivel!.puntos_ganados} puntos ⭐</Text>
            </View>
            {(resultadoNivel?.posicion_ranking ?? 0) > 0 && (
              <Text style={styles.rankingText}>
                Estás en el puesto #{resultadoNivel!.posicion_ranking} de tu grado
                {resultadoNivel!.cambio_posicion > 0
                  ? `  ¡Subiste ${resultadoNivel!.cambio_posicion} ${resultadoNivel!.cambio_posicion === 1 ? "puesto" : "puestos"}! 🚀`
                  : ""}
              </Text>
            )}
          </View>
        )}

        <View style={styles.statsRow}>
          {[
            { v: `${aciertos}/${total}`, l: "correctas", c: Colors.green },
            { v: `${promedio}`, l: "promedio", c: Colors.orange },
            { v: tiempo, l: "tiempo", c: Colors.blue },
          ].map((s) => (
            <View key={s.l} style={styles.statBox}>
              <Text style={[styles.statVal, { color: s.c }]}>{s.v}</Text>
              <Text style={styles.statLabel}>{s.l}</Text>
            </View>
          ))}
        </View>

        {aprobado && !domino && (
          <Pressable onPress={irEstudiar} style={[styles.botonGrande, { backgroundColor: Colors.green, marginTop: 24, paddingHorizontal: 32 }]}>
            <Text style={[styles.botonGrandeText, { fontSize: 16 }]}>Continuar al Nivel {nivel + 1} →</Text>
          </Pressable>
        )}
        {!aprobado && (
          <Pressable onPress={irEstudiar} style={[styles.botonGrande, { backgroundColor: Colors.orange, marginTop: 24, paddingHorizontal: 32 }]}>
            <Text style={[styles.botonGrandeText, { fontSize: 16 }]}>Intentar de nuevo 🔄</Text>
          </Pressable>
        )}

        {aprobado && (resultadoNivel?.posicion_ranking ?? 0) > 0 && (
          <Pressable
            onPress={() => router.replace("/(tabs)/ranking")}
            style={{ marginTop: 14, paddingVertical: 10 }}
          >
            <Text style={{ color: Colors.white, fontWeight: "800", fontSize: 14 }}>Ver ranking completo 🏆</Text>
          </Pressable>
        )}

        <Pressable onPress={() => router.dismissAll()} style={{ marginTop: 14, paddingVertical: 10 }}>
          <Text style={{ color: Colors.white, fontWeight: "800", fontSize: 14 }}>Volver a Mi Ruta</Text>
        </Pressable>
      </View>
    );
  }

  // ---------------- Ejercicio ----------------
  const elementos = (contenido.elementos_desordenados as string[]) ?? [];
  const disponibles = elementos.filter((e) => !orden.includes(e));
  const pregunta =
    act.tipo === "verdadero_falso"
      ? str("afirmacion")
      : act.tipo === "completar"
        ? str("oracion")
        : act.tipo === "ordenar"
          ? str("instruccion")
          : str("pregunta");

  return (
    <KeyboardAvoidingView
      style={styles.ejRoot}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <StatusBar style="light" />
      {/* Header: X + barra de bolitas */}
      <View style={[styles.ejHeader, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={abandonar} style={styles.x} hitSlop={10}>
          <Text style={styles.xText}>✕</Text>
        </Pressable>
        <View style={styles.dots}>
          {acts.map((_, i) => (
            <View key={i} style={[styles.dot, { backgroundColor: i <= idx ? Colors.orange : "rgba(255,255,255,0.18)" }]} />
          ))}
        </View>
        <Text style={styles.pasoText}>
          {idx + 1}/{acts.length}
        </Text>
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, paddingBottom: 24 }} keyboardShouldPersistTaps="handled">
        <Text style={styles.tipoLabel}>{act.tipo.replace("_", " ").toUpperCase()}</Text>
        <Text style={styles.pregunta}>{pregunta}</Text>

        {/* opción múltiple */}
        {act.tipo === "opcion_multiple" &&
          ((contenido.opciones as string[]) ?? []).map((op) => {
            const on = seleccion === op;
            return (
              <Pressable key={op} onPress={() => !feedback && setSeleccion(op)} style={[styles.opcion, on && styles.opcionOn]}>
                <Text style={styles.opcionText}>{op}</Text>
              </Pressable>
            );
          })}

        {/* verdadero / falso */}
        {act.tipo === "verdadero_falso" && (
          <View style={{ flexDirection: "row", gap: 12 }}>
            {[
              { val: "true", label: "✅ Verdadero", c: Colors.green },
              { val: "false", label: "❌ Falso", c: Colors.red },
            ].map((o) => {
              const on = seleccion === o.val;
              return (
                <Pressable
                  key={o.val}
                  onPress={() => !feedback && setSeleccion(o.val)}
                  style={[styles.vf, { borderColor: on ? o.c : "rgba(255,255,255,0.18)", backgroundColor: on ? o.c + "33" : "rgba(255,255,255,0.06)" }]}
                >
                  <Text style={styles.vfText}>{o.label}</Text>
                </Pressable>
              );
            })}
          </View>
        )}

        {/* completar */}
        {act.tipo === "completar" && (
          <View>
            <TextInput
              value={seleccion}
              onChangeText={setSeleccion}
              editable={!feedback}
              placeholder="Escribe la palabra que falta…"
              placeholderTextColor="rgba(255,255,255,0.4)"
              style={styles.input}
            />
            {!!str("pista") && <Text style={styles.pista}>💡 Pista: {str("pista")}</Text>}
          </View>
        )}

        {/* ordenar (tap para agregar / quitar) */}
        {act.tipo === "ordenar" && (
          <View>
            <Text style={styles.subLabel}>Tu orden (toca para quitar):</Text>
            <View style={styles.chips}>
              {orden.length === 0 && <Text style={styles.hint}>Toca los elementos de abajo en orden.</Text>}
              {orden.map((el, i) => (
                <Pressable key={el} onPress={() => !feedback && setOrden(orden.filter((x) => x !== el))} style={[styles.chip, styles.chipOn]}>
                  <Text style={styles.chipText}>
                    {i + 1}. {el}
                  </Text>
                </Pressable>
              ))}
            </View>
            <Text style={[styles.subLabel, { marginTop: 14 }]}>Disponibles:</Text>
            <View style={styles.chips}>
              {disponibles.map((el) => (
                <Pressable key={el} onPress={() => !feedback && setOrden([...orden, el])} style={styles.chip}>
                  <Text style={styles.chipText}>{el}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        )}

        {/* respuesta corta */}
        {act.tipo === "respuesta_corta" && (
          <TextInput
            value={seleccion}
            onChangeText={setSeleccion}
            editable={!feedback}
            placeholder="Escribe tu respuesta…"
            placeholderTextColor="rgba(255,255,255,0.4)"
            multiline
            style={[styles.input, { minHeight: 100, textAlignVertical: "top" }]}
          />
        )}
      </ScrollView>

      {/* Footer: Confirmar (si no hay feedback) */}
      {!feedback && (
        <View style={[styles.footer, { paddingBottom: insets.bottom + 12 }]}>
          <Pressable
            onPress={confirmar}
            disabled={!respuestaLista() || enviando}
            style={[styles.confirmar, { opacity: !respuestaLista() || enviando ? 0.4 : 1 }]}
          >
            <Text style={styles.confirmarText}>{enviando ? "Revisando…" : "Comprobar"}</Text>
          </Pressable>
        </View>
      )}

      {/* Panel de feedback (sube desde abajo) */}
      {feedback && <FeedbackPanel act={act} feedback={feedback} anim={panelAnim} bottomInset={insets.bottom} onContinuar={continuar} />}
    </KeyboardAvoidingView>
  );
}

function FeedbackPanel({
  act,
  feedback,
  anim,
  bottomInset,
  onContinuar,
}: {
  act: ActividadResponse;
  feedback: ResultadoResponse;
  anim: Animated.Value;
  bottomInset: number;
  onContinuar: () => void;
}) {
  const p = feedback.puntaje;
  const tono =
    p === 100
      ? { bg: "#DCFCE7", border: Colors.green, color: "#15803D", title: "¡Excelente! 🌟" }
      : p >= 60
        ? { bg: "#FEF9C3", border: "#F59E0B", color: "#B45309", title: "¡Casi! 💪" }
        : { bg: "#FEE2E2", border: Colors.red, color: "#B91C1C", title: "Incorrecto" };

  const rc = feedback.respuesta_correcta as Record<string, unknown>;
  const correcta =
    act.tipo === "ordenar"
      ? ((rc.orden_correcto as string[]) ?? []).join(" → ")
      : act.tipo === "verdadero_falso"
        ? rc.respuesta_correcta
          ? "Verdadero"
          : "Falso"
        : String(rc.respuesta_correcta ?? "");

  const translateY = anim.interpolate({ inputRange: [0, 1], outputRange: [340, 0] });

  return (
    <Animated.View
      style={[styles.panel, { backgroundColor: tono.bg, borderColor: tono.border, paddingBottom: bottomInset + 16, transform: [{ translateY }] }]}
    >
      <Text style={[styles.panelTitulo, { color: tono.color }]}>{tono.title}</Text>
      {p < 100 && !!correcta && (
        <Text style={[styles.panelCorrecta, { color: tono.color }]}>Respuesta correcta: {correcta}</Text>
      )}
      <Text style={styles.panelRetro}>{feedback.retroalimentacion}</Text>
      <Pressable onPress={onContinuar} style={[styles.continuar, { backgroundColor: tono.border }]}>
        <Text style={styles.continuarText}>Continuar</Text>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  centro: { flex: 1, backgroundColor: Colors.navy, alignItems: "center", justifyContent: "center" },
  bigEmoji: { fontSize: 72 },
  cargandoTitulo: { fontSize: 21, fontWeight: "900", color: Colors.white, marginTop: 12, textAlign: "center" },
  botonGrande: { borderRadius: 18, paddingHorizontal: 28, paddingVertical: 15, alignItems: "center" },
  botonGrandeText: { color: Colors.white, fontWeight: "900", fontSize: 15 },

  // resultados
  starsRow: { fontSize: 40, marginBottom: 8 },
  resultTitulo: { fontSize: 30, fontWeight: "900", color: Colors.white, textAlign: "center" },
  resultMensaje: { fontSize: 14, fontWeight: "700", color: "rgba(255,255,255,0.7)", textAlign: "center", marginTop: 8 },
  puntosBadge: {
    backgroundColor: Colors.orange,
    borderRadius: 999,
    paddingHorizontal: 22,
    paddingVertical: 8,
    marginTop: 14,
  },
  puntosBadgeText: { fontSize: 20, fontWeight: "900", color: Colors.white },
  rankingText: { fontSize: 13, fontWeight: "800", color: "rgba(255,255,255,0.85)", textAlign: "center" },
  statsRow: { flexDirection: "row", gap: 12, marginTop: 22 },
  statBox: { backgroundColor: "rgba(255,255,255,0.1)", borderRadius: 16, paddingHorizontal: 22, paddingVertical: 14, alignItems: "center" },
  statVal: { fontSize: 26, fontWeight: "900" },
  statLabel: { fontSize: 11, fontWeight: "800", color: "rgba(255,255,255,0.6)" },
  desbloqueo: { marginTop: 18, backgroundColor: "rgba(34,197,94,0.2)", borderRadius: 999, paddingHorizontal: 20, paddingVertical: 12 },
  desbloqueoText: { color: Colors.green, fontWeight: "900", fontSize: 15 },

  // ejercicio
  ejRoot: { flex: 1, backgroundColor: Colors.navy },
  ejHeader: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12 },
  x: { width: 34, height: 34, borderRadius: 17, backgroundColor: "rgba(255,255,255,0.12)", alignItems: "center", justifyContent: "center" },
  xText: { color: "rgba(255,255,255,0.85)", fontSize: 16, fontWeight: "900" },
  dots: { flex: 1, flexDirection: "row", gap: 6 },
  dot: { flex: 1, height: 10, borderRadius: 5 },
  pasoText: { color: "rgba(255,255,255,0.7)", fontWeight: "800", fontSize: 13 },
  tipoLabel: { color: Colors.orange, fontSize: 12, fontWeight: "800", letterSpacing: 1, marginBottom: 6 },
  pregunta: { color: Colors.white, fontSize: 23, fontWeight: "900", lineHeight: 30, marginBottom: 24 },
  opcion: { borderWidth: 2, borderColor: "rgba(255,255,255,0.18)", backgroundColor: "rgba(255,255,255,0.06)", borderRadius: 16, paddingHorizontal: 18, paddingVertical: 16, marginBottom: 12 },
  opcionOn: { borderColor: Colors.orange, backgroundColor: "rgba(249,115,22,0.18)" },
  opcionText: { color: Colors.white, fontSize: 16, fontWeight: "700" },
  vf: { flex: 1, borderWidth: 2, borderRadius: 16, paddingVertical: 28, alignItems: "center" },
  vfText: { color: Colors.white, fontSize: 17, fontWeight: "900" },
  input: { borderWidth: 2, borderColor: "rgba(255,255,255,0.2)", backgroundColor: "rgba(255,255,255,0.1)", borderRadius: 16, paddingHorizontal: 18, paddingVertical: 14, color: Colors.white, fontSize: 16, fontWeight: "600" },
  pista: { color: "rgba(255,255,255,0.8)", fontWeight: "800", fontSize: 13, marginTop: 12 },
  subLabel: { color: "rgba(255,255,255,0.6)", fontWeight: "800", fontSize: 12.5, marginBottom: 8 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  hint: { color: "rgba(255,255,255,0.45)", fontWeight: "700", fontSize: 13 },
  chip: { borderWidth: 2, borderColor: "rgba(255,255,255,0.18)", backgroundColor: "rgba(255,255,255,0.06)", borderRadius: 14, paddingHorizontal: 14, paddingVertical: 10 },
  chipOn: { borderColor: Colors.orange, backgroundColor: "rgba(249,115,22,0.18)" },
  chipText: { color: Colors.white, fontSize: 14.5, fontWeight: "700" },
  footer: { paddingHorizontal: 20, paddingTop: 12, backgroundColor: Colors.navy, borderTopWidth: 1, borderTopColor: "rgba(255,255,255,0.08)" },
  confirmar: { backgroundColor: Colors.orange, borderRadius: 18, paddingVertical: 16, alignItems: "center" },
  confirmarText: { color: Colors.white, fontSize: 17, fontWeight: "900" },

  // panel feedback
  panel: { position: "absolute", left: 0, right: 0, bottom: 0, borderTopWidth: 4, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingHorizontal: 22, paddingTop: 20 },
  panelTitulo: { fontSize: 22, fontWeight: "900" },
  panelCorrecta: { fontSize: 14, fontWeight: "800", marginTop: 4 },
  panelRetro: { fontSize: 14, fontWeight: "600", color: "#3f3f46", marginTop: 6 },
  continuar: { borderRadius: 16, paddingVertical: 15, alignItems: "center", marginTop: 16 },
  continuarText: { color: Colors.white, fontSize: 16, fontWeight: "900" },
});
