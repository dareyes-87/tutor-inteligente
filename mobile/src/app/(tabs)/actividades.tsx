import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  generarActividad,
  obtenerMisLibros,
  obtenerRuta,
  responderActividad,
  TIPO_ETIQUETA,
  type ActividadResponse,
  type LeccionEnRuta,
  type LibroDisponible,
  type ResultadoResponse,
  type TipoActividad,
} from "@/lib/api";
import { Colors } from "@/lib/colors";

// Práctica libre / repaso (igual que la página Actividades de la web): cualquier lección del
// libro, también las bloqueadas en la ruta. Cuenta para el perfil por tema y el mapa de calor
// del docente, pero NO toca la ruta: aquí nunca se llama a completar-actividad.
const TIPOS: { key: TipoActividad; icon: string }[] = [
  { key: "opcion_multiple", icon: "☑️" },
  { key: "verdadero_falso", icon: "⚖️" },
  { key: "completar", icon: "✏️" },
  { key: "ordenar", icon: "🔢" },
  { key: "respuesta_corta", icon: "💬" },
];

type Fase = "seleccion" | "generando" | "respondiendo" | "resultado";

function textoPregunta(a: ActividadResponse): string | null {
  const c = a.contenido as Record<string, unknown>;
  const t = c.pregunta ?? c.afirmacion ?? c.oracion ?? c.instruccion;
  return typeof t === "string" && t.trim() ? t : null;
}

export default function ActividadesScreen() {
  // Desde Mi progreso (asignatura + tema) o el chat (asignatura + lección).
  const params = useLocalSearchParams<{ asignatura?: string; tema?: string; leccion?: string; t?: string }>();
  const [libros, setLibros] = useState<LibroDisponible[]>([]);
  const [libroId, setLibroId] = useState<number | null>(null);
  const [lecciones, setLecciones] = useState<LeccionEnRuta[]>([]);
  const [leccionId, setLeccionId] = useState<number | null>(null);
  const [tema, setTema] = useState("");
  const leccionPedida = useRef<number | null>(null);
  const libro = libros.find((l) => l.libro_id === libroId) ?? null;

  const [fase, setFase] = useState<Fase>("seleccion");
  const [actividad, setActividad] = useState<ActividadResponse | null>(null);
  const [resultado, setResultado] = useState<ResultadoResponse | null>(null);
  const [seleccion, setSeleccion] = useState("");
  const [orden, setOrden] = useState<string[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Preguntas ya salidas en esta sesión: "Otra igual" se las pasa al generador para no repetirlas.
  const preguntasSesion = useRef<string[]>([]);

  // Libros del grado + parámetros de navegación (cada navegación trae `t` distinto).
  useEffect(() => {
    let activo = true;
    obtenerMisLibros()
      .then((ls) => {
        if (!activo) return;
        const pedido = ls.find((l) => l.asignatura_id === Number(params.asignatura));
        leccionPedida.current = Number(params.leccion) || null;
        setLibros(ls);
        setTema(params.tema ?? "");
        setFase("seleccion");
        setLibroId((actual) => (pedido ?? ls.find((l) => l.libro_id === actual) ?? ls[0])?.libro_id ?? null);
      })
      .catch(() => activo && setError("No se pudieron cargar tus libros"));
    return () => {
      activo = false;
    };
  }, [params.asignatura, params.tema, params.leccion, params.t]);

  // Lecciones del libro elegido (todas, con su estado en la ruta).
  useEffect(() => {
    if (libroId === null) return;
    let activo = true;
    obtenerRuta(libroId)
      .then((r) => {
        if (!activo) return;
        setLecciones(r.lecciones);
        const pedida = r.lecciones.find((l) => l.id === leccionPedida.current);
        setLeccionId(pedida ? pedida.id : null);
        leccionPedida.current = null;
      })
      .catch(() => activo && setLecciones([]));
    return () => {
      activo = false;
    };
  }, [libroId, params.t]);

  async function generar(tipo: TipoActividad) {
    if (!libro) return;
    setFase("generando");
    setError(null);
    setActividad(null);
    setResultado(null);
    setSeleccion("");
    setOrden([]);
    try {
      const act = await generarActividad(
        libro.asignatura_id,
        tipo,
        leccionId ? "" : tema.trim(),
        leccionId,
        [],
        preguntasSesion.current,
      );
      const texto = textoPregunta(act);
      if (texto) preguntasSesion.current = [...preguntasSesion.current, texto];
      setActividad(act);
      setFase("respondiendo");
    } catch {
      setError("No se pudo generar la actividad. Intenta de nuevo.");
      setFase("seleccion");
    }
  }

  async function enviar() {
    if (!actividad || enviando) return;
    setEnviando(true);
    try {
      const respuesta =
        actividad.tipo === "verdadero_falso"
          ? { respuesta: seleccion === "true" }
          : actividad.tipo === "ordenar"
            ? { orden }
            : { respuesta: seleccion };
      setResultado(await responderActividad(actividad.id, respuesta));
      setFase("resultado");
    } catch {
      setError("No se pudo enviar tu respuesta. Intenta de nuevo.");
    } finally {
      setEnviando(false);
    }
  }

  const cambiarTipo = () => {
    setFase("seleccion");
    setActividad(null);
    setResultado(null);
  };

  const listo =
    actividad?.tipo === "ordenar"
      ? orden.length === ((actividad.contenido.elementos_desordenados as string[]) ?? []).length
      : seleccion.trim() !== "";

  return (
    <SafeAreaView style={styles.root} edges={["top"]}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior="padding">
        <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 32 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.titulo}>Actividades</Text>
          <Text style={styles.subtitulo}>
            Práctica libre / repaso{libro ? ` · ${libro.asignatura_nombre}` : ""}
          </Text>
          {!!error && <Text style={styles.error}>{error}</Text>}

          {fase === "seleccion" && (
            <Seleccion
              libros={libros}
              libroId={libroId}
              setLibroId={(id) => {
                setLibroId(id);
                setLeccionId(null);
              }}
              lecciones={lecciones}
              leccionId={leccionId}
              setLeccionId={setLeccionId}
              tema={tema}
              setTema={setTema}
              onGenerar={generar}
            />
          )}

          {fase === "generando" && (
            <View style={styles.card}>
              <ActivityIndicator color={Colors.orange} size="large" />
              <Text style={[styles.cardTitulo, { textAlign: "center", marginTop: 12 }]}>Generando tu actividad…</Text>
              <Text style={[styles.nota, { textAlign: "center" }]}>El tutor prepara una pregunta desde tu libro.</Text>
            </View>
          )}

          {fase === "respondiendo" && actividad && (
            <View style={styles.card}>
              <Text style={styles.tipoChip}>
                {TIPO_ETIQUETA[actividad.tipo]}
                {actividad.tema ? ` · ${actividad.tema}` : ""}
              </Text>
              <Text style={styles.pregunta}>{textoPregunta(actividad)}</Text>
              <Respuesta
                actividad={actividad}
                seleccion={seleccion}
                setSeleccion={setSeleccion}
                orden={orden}
                setOrden={setOrden}
              />
              <View style={styles.filaBotones}>
                <Pressable onPress={cambiarTipo} style={styles.botonSec}>
                  <Text style={styles.botonSecText}>← Cambiar tipo</Text>
                </Pressable>
                <Pressable
                  onPress={enviar}
                  disabled={!listo || enviando}
                  style={[styles.botonPri, { opacity: !listo || enviando ? 0.5 : 1 }]}
                >
                  <Text style={styles.botonPriText}>{enviando ? "Revisando…" : "Enviar"}</Text>
                </Pressable>
              </View>
            </View>
          )}

          {fase === "resultado" && actividad && resultado && (
            <Resultado
              actividad={actividad}
              resultado={resultado}
              onOtraIgual={() => generar(actividad.tipo)}
              onCambiarTipo={cambiarTipo}
            />
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Seleccion({
  libros,
  libroId,
  setLibroId,
  lecciones,
  leccionId,
  setLeccionId,
  tema,
  setTema,
  onGenerar,
}: {
  libros: LibroDisponible[];
  libroId: number | null;
  setLibroId: (id: number) => void;
  lecciones: LeccionEnRuta[];
  leccionId: number | null;
  setLeccionId: (id: number | null) => void;
  tema: string;
  setTema: (t: string) => void;
  onGenerar: (t: TipoActividad) => void;
}) {
  const [verLecciones, setVerLecciones] = useState(false);
  const elegida = lecciones.find((l) => l.id === leccionId);
  return (
    <View>
      {libros.length > 1 && (
        <>
          <Text style={styles.etiqueta}>Asignatura</Text>
          <View style={styles.chips}>
            {libros.map((l) => {
              const on = l.libro_id === libroId;
              return (
                <Pressable
                  key={l.libro_id}
                  onPress={() => setLibroId(l.libro_id)}
                  style={[styles.chip, on && styles.chipOn]}
                  accessibilityState={{ selected: on }}
                >
                  <Text style={[styles.chipText, on && { color: Colors.white }]}>{l.asignatura_nombre}</Text>
                </Pressable>
              );
            })}
          </View>
        </>
      )}

      <Text style={styles.etiqueta}>Lección · práctica libre / repaso</Text>
      <Pressable onPress={() => setVerLecciones((v) => !v)} style={styles.selector} accessibilityRole="button">
        <Text style={styles.selectorText} numberOfLines={1}>
          {elegida
            ? `${elegida.estado === "bloqueada" ? "🔒 " : ""}Lección ${elegida.orden} · ${elegida.nombre}`
            : "Cualquier tema del libro"}
        </Text>
        <Text style={styles.selectorText}>{verLecciones ? "▲" : "▼"}</Text>
      </Pressable>
      {verLecciones && (
        <View style={styles.lista}>
          {[null, ...lecciones].map((l) => (
            <Pressable
              key={l?.id ?? 0}
              onPress={() => {
                setLeccionId(l?.id ?? null);
                setVerLecciones(false);
              }}
              style={[styles.listaItem, (l?.id ?? null) === leccionId && { backgroundColor: Colors.grayLight }]}
            >
              <Text style={styles.listaText} numberOfLines={2}>
                {l ? `${l.estado === "bloqueada" ? "🔒 " : ""}Lección ${l.orden} · ${l.nombre}` : "Cualquier tema del libro"}
              </Text>
            </Pressable>
          ))}
        </View>
      )}
      <Text style={styles.nota}>
        Puedes repasar cualquier lección, también las que aún no desbloqueas. La práctica libre cuenta
        para tu progreso por tema, pero no cambia tu ruta (niveles ni estrellas).
      </Text>

      {leccionId === null && (
        <>
          <Text style={styles.etiqueta}>Tema (opcional)</Text>
          <TextInput
            value={tema}
            onChangeText={setTema}
            placeholder="Ej: el ciclo del agua, las plantas…"
            placeholderTextColor={Colors.gray}
            style={styles.input}
          />
        </>
      )}

      {TIPOS.map((t) => (
        <View key={t.key} style={styles.tipoCard}>
          <Text style={{ fontSize: 26 }}>{t.icon}</Text>
          <Text style={styles.tipoNombre}>{TIPO_ETIQUETA[t.key]}</Text>
          <Pressable onPress={() => onGenerar(t.key)} style={styles.botonPri} disabled={libroId === null}>
            <Text style={styles.botonPriText}>Practicar</Text>
          </Pressable>
        </View>
      ))}
    </View>
  );
}

function Respuesta({
  actividad,
  seleccion,
  setSeleccion,
  orden,
  setOrden,
}: {
  actividad: ActividadResponse;
  seleccion: string;
  setSeleccion: (v: string) => void;
  orden: string[];
  setOrden: (v: string[]) => void;
}) {
  const c = actividad.contenido as Record<string, unknown>;
  if (actividad.tipo === "opcion_multiple") {
    return (
      <>
        {((c.opciones as string[]) ?? []).map((op) => (
          <Pressable key={op} onPress={() => setSeleccion(op)} style={[styles.opcion, seleccion === op && styles.opcionOn]}>
            <Text style={styles.opcionText}>{op}</Text>
          </Pressable>
        ))}
      </>
    );
  }
  if (actividad.tipo === "verdadero_falso") {
    return (
      <View style={{ flexDirection: "row", gap: 10 }}>
        {[
          { val: "true", label: "✅ Verdadero" },
          { val: "false", label: "❌ Falso" },
        ].map((o) => (
          <Pressable
            key={o.val}
            onPress={() => setSeleccion(o.val)}
            style={[styles.opcion, { flex: 1 }, seleccion === o.val && styles.opcionOn]}
          >
            <Text style={[styles.opcionText, { textAlign: "center" }]}>{o.label}</Text>
          </Pressable>
        ))}
      </View>
    );
  }
  if (actividad.tipo === "ordenar") {
    const elementos = (c.elementos_desordenados as string[]) ?? [];
    return (
      <View>
        <Text style={styles.nota}>Tu orden (toca para quitar):</Text>
        <View style={styles.chips}>
          {orden.map((el, i) => (
            <Pressable key={el} onPress={() => setOrden(orden.filter((x) => x !== el))} style={[styles.chip, styles.chipOn]}>
              <Text style={[styles.chipText, { color: Colors.white }]}>
                {i + 1}. {el}
              </Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.nota}>Disponibles:</Text>
        <View style={styles.chips}>
          {elementos
            .filter((e) => !orden.includes(e))
            .map((el) => (
              <Pressable key={el} onPress={() => setOrden([...orden, el])} style={styles.chip}>
                <Text style={styles.chipText}>{el}</Text>
              </Pressable>
            ))}
        </View>
      </View>
    );
  }
  return (
    <View>
      <TextInput
        value={seleccion}
        onChangeText={setSeleccion}
        placeholder={actividad.tipo === "completar" ? "Escribe la palabra que falta…" : "Escribe tu respuesta…"}
        placeholderTextColor={Colors.gray}
        multiline={actividad.tipo === "respuesta_corta"}
        style={[styles.input, actividad.tipo === "respuesta_corta" && { minHeight: 90, textAlignVertical: "top" }]}
      />
      {actividad.tipo === "completar" && typeof c.pista === "string" && !!c.pista && (
        <Text style={styles.nota}>💡 Pista: {c.pista}</Text>
      )}
    </View>
  );
}

function Resultado({
  actividad,
  resultado,
  onOtraIgual,
  onCambiarTipo,
}: {
  actividad: ActividadResponse;
  resultado: ResultadoResponse;
  onOtraIgual: () => void;
  onCambiarTipo: () => void;
}) {
  const aprobado = resultado.puntaje >= 60;
  const rc = resultado.respuesta_correcta;
  const correcta =
    actividad.tipo === "ordenar"
      ? ((rc.orden_correcto as string[]) ?? []).join("  →  ")
      : actividad.tipo === "verdadero_falso"
        ? rc.respuesta_correcta
          ? "Verdadero"
          : "Falso"
        : String(rc.respuesta_correcta ?? "");
  return (
    <View style={[styles.card, { borderColor: aprobado ? "#BBF7D0" : "#FECACA", borderWidth: 2 }]}>
      <Text style={[styles.resultTitulo, { color: aprobado ? "#16A34A" : "#DC2626" }]}>
        {aprobado ? "¡Bien hecho! 🎉" : "¡Casi! Inténtalo otra vez 💪"}
      </Text>
      <Text style={styles.puntaje}>{Math.round(resultado.puntaje)} / 100 ⭐</Text>
      {/* La retroalimentación trae la página del libro ("📖 Repasa tu libro…"). */}
      <Text style={styles.retro}>{resultado.retroalimentacion}</Text>
      {!!correcta && (
        <Text style={styles.correcta}>
          Respuesta correcta: <Text style={{ color: Colors.green }}>{correcta}</Text>
        </Text>
      )}
      <View style={styles.filaBotones}>
        <Pressable onPress={onCambiarTipo} style={styles.botonSec}>
          <Text style={styles.botonSecText}>← Cambiar tipo</Text>
        </Pressable>
        <Pressable onPress={onOtraIgual} style={styles.botonPri}>
          <Text style={styles.botonPriText}>🔁 Otra igual</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.cream },
  titulo: { fontSize: 24, fontWeight: "900", color: Colors.navy },
  subtitulo: { fontSize: 14, fontWeight: "700", color: Colors.textLight, marginTop: 3, marginBottom: 16 },
  error: { color: Colors.red, fontWeight: "800", marginBottom: 12 },
  etiqueta: { fontSize: 13, fontWeight: "800", color: "#5A6170", marginBottom: 7, marginTop: 6 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 12 },
  chip: { borderRadius: 999, paddingHorizontal: 14, paddingVertical: 9, backgroundColor: Colors.white, borderWidth: 2, borderColor: Colors.border },
  chipOn: { backgroundColor: Colors.blue, borderColor: Colors.blue },
  chipText: { fontSize: 13.5, fontWeight: "800", color: Colors.navy },
  selector: { flexDirection: "row", justifyContent: "space-between", gap: 8, backgroundColor: Colors.white, borderRadius: 14, borderWidth: 2, borderColor: Colors.border, padding: 14 },
  selectorText: { flexShrink: 1, fontSize: 14.5, fontWeight: "700", color: Colors.navy },
  lista: { backgroundColor: Colors.white, borderRadius: 14, borderWidth: 1, borderColor: Colors.border, marginTop: 6, maxHeight: 320, overflow: "hidden" },
  listaItem: { paddingHorizontal: 14, paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: Colors.border },
  listaText: { fontSize: 14, fontWeight: "700", color: Colors.navy },
  nota: { fontSize: 12.5, fontWeight: "700", color: Colors.textLight, marginTop: 8, marginBottom: 10 },
  input: { backgroundColor: Colors.white, borderRadius: 14, borderWidth: 2, borderColor: Colors.border, padding: 14, fontSize: 15, fontWeight: "600", color: Colors.navy, marginBottom: 14 },
  tipoCard: { flexDirection: "row", alignItems: "center", gap: 14, backgroundColor: Colors.white, borderRadius: 18, borderWidth: 1, borderColor: Colors.border, padding: 14, marginBottom: 10 },
  tipoNombre: { flex: 1, fontSize: 15, fontWeight: "800", color: Colors.navy },
  card: { backgroundColor: Colors.white, borderRadius: 20, borderWidth: 1, borderColor: Colors.border, padding: 18 },
  cardTitulo: { fontSize: 17, fontWeight: "900", color: Colors.navy },
  tipoChip: { alignSelf: "flex-start", fontSize: 12, fontWeight: "800", color: Colors.blue, backgroundColor: "#EAF1FF", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, marginBottom: 12, overflow: "hidden" },
  pregunta: { fontSize: 18, fontWeight: "800", color: Colors.navy, marginBottom: 14, lineHeight: 25 },
  opcion: { borderRadius: 14, borderWidth: 2, borderColor: Colors.border, backgroundColor: Colors.grayLight, padding: 14, marginBottom: 10 },
  opcionOn: { borderColor: Colors.blue, backgroundColor: "#EAF1FF" },
  opcionText: { fontSize: 15, fontWeight: "700", color: Colors.navy },
  filaBotones: { flexDirection: "row", gap: 10, marginTop: 14, flexWrap: "wrap" },
  botonPri: { backgroundColor: Colors.blue, borderRadius: 14, paddingHorizontal: 18, paddingVertical: 12, alignItems: "center" },
  botonPriText: { color: Colors.white, fontSize: 14.5, fontWeight: "900" },
  botonSec: { borderRadius: 14, borderWidth: 2, borderColor: Colors.border, backgroundColor: Colors.white, paddingHorizontal: 16, paddingVertical: 11, alignItems: "center" },
  botonSecText: { color: "#5A6170", fontSize: 14.5, fontWeight: "800" },
  resultTitulo: { fontSize: 21, fontWeight: "900", textAlign: "center" },
  puntaje: { fontSize: 16, fontWeight: "900", color: Colors.navy, textAlign: "center", marginTop: 8 },
  retro: { fontSize: 14.5, fontWeight: "600", color: "#5A6170", lineHeight: 21, marginTop: 12 },
  correcta: { fontSize: 14, fontWeight: "800", color: Colors.navy, marginTop: 12 },
});
