import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  KeyboardAvoidingView,
  Modal,
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
  obtenerMicroLeccion,
  preguntar,
  type MicroLeccion,
  type TarjetaEducativa,
} from "@/lib/api";
import { Colors } from "@/lib/colors";

const ASIGNATURA_ID = 1;

export default function EstudiarScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const leccionId = Number(id);
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [micro, setMicro] = useState<MicroLeccion | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(false);

  const [idx, setIdx] = useState(0);
  const [mostrarPregunta, setMostrarPregunta] = useState(false);
  const [seleccion, setSeleccion] = useState<string | null>(null);
  const [chatAbierto, setChatAbierto] = useState(false);

  const fade = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    let activo = true;
    (async () => {
      try {
        const m = await obtenerMicroLeccion(leccionId);
        if (!activo) return;
        setMicro(m);
        setError(false);
      } catch {
        if (activo) setError(true);
      } finally {
        if (activo) setCargando(false);
      }
    })();
    return () => {
      activo = false;
    };
  }, [leccionId]);

  // Reinicia estado de pregunta y anima la entrada al cambiar de tarjeta.
  useEffect(() => {
    setMostrarPregunta(false);
    setSeleccion(null);
    fade.setValue(0);
    Animated.timing(fade, { toValue: 1, duration: 320, useNativeDriver: true }).start();
  }, [idx, fade]);

  const tarjetas = micro?.tarjetas ?? [];
  const total = tarjetas.length;
  const tarjeta = tarjetas[idx] as TarjetaEducativa | undefined;
  const esUltima = idx >= total - 1;

  function avanzar() {
    if (esUltima) {
      router.push({ pathname: "/leccion/[id]/practicar", params: { id: String(leccionId) } });
      return;
    }
    setIdx((i) => i + 1);
  }

  if (cargando) {
    return (
      <View style={[styles.root, styles.center]}>
        <StatusBar style="light" />
        <ActivityIndicator color={Colors.orange} size="large" />
        <Text style={styles.cargandoText}>🐯 Preparando tu lección…</Text>
      </View>
    );
  }

  if (error || !micro || total === 0 || !tarjeta) {
    return (
      <View style={[styles.root, styles.center, { padding: 24 }]}>
        <StatusBar style="light" />
        <Text style={{ fontSize: 44 }}>😕</Text>
        <Text style={styles.errorText}>No pudimos preparar esta lección. Intenta de nuevo.</Text>
        <Pressable onPress={() => router.back()} style={styles.volverBtn}>
          <Text style={styles.volverText}>Volver a la ruta</Text>
        </Pressable>
      </View>
    );
  }

  const esConcepto = tarjeta.tipo === "concepto";
  const tienePregunta = esConcepto && tarjeta.pregunta != null;
  const respondida = seleccion != null;
  const correcta = respondida && seleccion === tarjeta.pregunta?.respuesta_correcta;

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <StatusBar style="light" />

      {/* Header + progreso */}
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.x} hitSlop={10}>
          <Text style={styles.xText}>✕</Text>
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitulo} numberOfLines={1}>
            📖 {micro.titulo}
          </Text>
          <View style={styles.barraBg}>
            <View style={[styles.barraFill, { width: `${((idx + 1) / total) * 100}%` }]} />
          </View>
        </View>
        <Text style={styles.contador}>
          {idx + 1}/{total}
        </Text>
      </View>

      {/* Tarjeta */}
      <ScrollView contentContainerStyle={styles.scroll}>
        <Animated.View style={[styles.tarjeta, { opacity: fade }]}>
          <Text style={styles.emoji}>{tarjeta.emoji}</Text>

          {tarjeta.tipo === "introduccion" && <Text style={styles.titulo}>¡Empecemos!</Text>}
          {esConcepto && !!tarjeta.titulo_concepto && (
            <Text style={styles.titulo}>{tarjeta.titulo_concepto}</Text>
          )}
          {tarjeta.tipo === "resumen" && <Text style={styles.titulo}>¡Lo lograste!</Text>}

          <Text style={styles.contenido}>{tarjeta.contenido}</Text>

          {!!tarjeta.dato_curioso && (
            <View style={styles.dato}>
              <Text style={styles.datoText}>💡 {tarjeta.dato_curioso}</Text>
            </View>
          )}

          {/* Pregunta de comprensión */}
          {tienePregunta && mostrarPregunta && tarjeta.pregunta && (
            <View style={styles.preguntaBox}>
              <Text style={styles.preguntaTexto}>{tarjeta.pregunta.texto}</Text>
              {tarjeta.pregunta.opciones.map((op) => {
                const esEsta = seleccion === op;
                const esCorrecta = op === tarjeta.pregunta!.respuesta_correcta;
                let estilo = styles.opcion;
                let color = Colors.navy;
                if (respondida) {
                  if (esCorrecta) {
                    estilo = styles.opcionCorrecta;
                    color = Colors.green;
                  } else if (esEsta) {
                    estilo = styles.opcionMal;
                    color = Colors.red;
                  } else {
                    estilo = styles.opcionApagada;
                    color = Colors.textLight;
                  }
                }
                return (
                  <Pressable
                    key={op}
                    disabled={respondida}
                    onPress={() => setSeleccion(op)}
                    style={[styles.opcionBase, estilo]}
                  >
                    <Text style={[styles.opcionText, { color }]}>{op}</Text>
                  </Pressable>
                );
              })}
              {respondida && (
                <View style={[styles.feedback, correcta ? styles.feedbackOk : styles.feedbackMal]}>
                  <Text style={[styles.feedbackText, { color: correcta ? Colors.green : Colors.red }]}>
                    {correcta ? "✅ ¡Correcto! " : "❌ Casi… "}
                    {tarjeta.pregunta.explicacion}
                  </Text>
                </View>
              )}
            </View>
          )}

          {esConcepto && (
            <Pressable onPress={() => setChatAbierto(true)} style={styles.preguntarTutor}>
              <Text style={styles.preguntarTutorText}>💬 Preguntar al tutor</Text>
            </Pressable>
          )}

          {/* Acción principal */}
          <View style={{ width: "100%", marginTop: 22 }}>
            {tarjeta.tipo === "introduccion" && (
              <BotonPrincipal label="Empecemos →" verde={false} onPress={avanzar} />
            )}
            {esConcepto && !tienePregunta && (
              <BotonPrincipal label="Continuar →" verde={false} onPress={avanzar} />
            )}
            {esConcepto && tienePregunta && !mostrarPregunta && (
              <BotonPrincipal label="Continuar →" verde={false} onPress={() => setMostrarPregunta(true)} />
            )}
            {esConcepto && tienePregunta && mostrarPregunta && (
              <BotonPrincipal label="Siguiente →" verde={false} disabled={!respondida} onPress={avanzar} />
            )}
            {tarjeta.tipo === "resumen" && (
              <BotonPrincipal label="Ir a Practicar 🎯" verde onPress={avanzar} />
            )}
          </View>
        </Animated.View>
      </ScrollView>

      <Modal visible={chatAbierto} animationType="slide" transparent onRequestClose={() => setChatAbierto(false)}>
        <MiniChat
          contexto={tarjeta.titulo_concepto ?? micro.titulo}
          onCerrar={() => setChatAbierto(false)}
        />
      </Modal>
    </View>
  );
}

function BotonPrincipal({
  label,
  verde,
  disabled,
  onPress,
}: {
  label: string;
  verde: boolean;
  disabled?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={[
        styles.principal,
        { backgroundColor: verde ? Colors.green : Colors.blue, opacity: disabled ? 0.5 : 1 },
      ]}
    >
      <Text style={styles.principalText}>{label}</Text>
    </Pressable>
  );
}

interface MiniMsg {
  rol: "tutor" | "me";
  texto: string;
}

function MiniChat({ contexto, onCerrar }: { contexto: string; onCerrar: () => void }) {
  const insets = useSafeAreaInsets();
  const [mensajes, setMensajes] = useState<MiniMsg[]>([]);
  const [conversacionId, setConversacionId] = useState<number | null>(null);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    scrollRef.current?.scrollToEnd({ animated: true });
  }, [mensajes, enviando]);

  async function enviar() {
    const t = texto.trim();
    if (!t || enviando) return;
    setMensajes((prev) => [...prev, { rol: "me", texto: t }]);
    setTexto("");
    setEnviando(true);
    try {
      const res = await preguntar(t, ASIGNATURA_ID, conversacionId);
      setConversacionId(res.conversacion_id);
      setMensajes((prev) => [...prev, { rol: "tutor", texto: res.respuesta }]);
    } catch {
      setMensajes((prev) => [...prev, { rol: "tutor", texto: "No pude responder ahora. Intenta de nuevo." }]);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <View style={styles.modalRoot}>
      <KeyboardAvoidingView
        style={styles.modalSheet}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={[styles.modalHeader, { paddingTop: 14 }]}>
          <View style={{ flex: 1 }}>
            <Text style={styles.modalTitulo}>💬 Tutor Tigre</Text>
            <Text style={styles.modalSub} numberOfLines={1}>
              Sobre: {contexto}
            </Text>
          </View>
          <Pressable onPress={onCerrar} style={styles.x} hitSlop={10}>
            <Text style={styles.xText}>✕</Text>
          </Pressable>
        </View>

        <ScrollView ref={scrollRef} style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 12 }}>
          {mensajes.length === 0 && !enviando && (
            <Text style={styles.modalHint}>Escríbeme una duda sobre {contexto} 🐯</Text>
          )}
          {mensajes.map((m, i) => (
            <View key={i} style={[styles.fila, m.rol === "me" ? styles.filaMe : styles.filaTutor]}>
              <View style={[styles.burbuja, m.rol === "me" ? styles.burbujaMe : styles.burbujaTutor]}>
                <Text style={[styles.burbujaText, { color: m.rol === "me" ? "#1E3A8A" : Colors.text }]}>
                  {m.texto}
                </Text>
              </View>
            </View>
          ))}
          {enviando && (
            <View style={[styles.fila, styles.filaTutor]}>
              <View style={[styles.burbuja, styles.burbujaTutor]}>
                <Text style={[styles.burbujaText, { color: Colors.textLight }]}>El tutor está escribiendo…</Text>
              </View>
            </View>
          )}
        </ScrollView>

        <View style={[styles.inputRow, { paddingBottom: insets.bottom + 8 }]}>
          <TextInput
            value={texto}
            onChangeText={setTexto}
            placeholder="Escribe tu duda…"
            placeholderTextColor="#B6BBC6"
            style={styles.input}
            onSubmitEditing={enviar}
            returnKeyType="send"
          />
          <Pressable
            onPress={enviar}
            disabled={enviando || !texto.trim()}
            style={[styles.enviar, { opacity: enviando || !texto.trim() ? 0.5 : 1 }]}
          >
            {enviando ? <ActivityIndicator color={Colors.white} /> : <Text style={styles.enviarText}>➤</Text>}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.navy },
  center: { alignItems: "center", justifyContent: "center", gap: 14 },
  cargandoText: { color: Colors.white, fontSize: 16, fontWeight: "900" },
  errorText: { color: Colors.white, fontSize: 15, fontWeight: "700", textAlign: "center" },
  volverBtn: { backgroundColor: Colors.blue, borderRadius: 16, paddingHorizontal: 24, paddingVertical: 12 },
  volverText: { color: Colors.white, fontWeight: "900", fontSize: 15 },

  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 12 },
  x: { width: 34, height: 34, borderRadius: 17, backgroundColor: "rgba(255,255,255,0.12)", alignItems: "center", justifyContent: "center" },
  xText: { color: "rgba(255,255,255,0.85)", fontSize: 16, fontWeight: "900" },
  headerTitulo: { color: Colors.white, fontSize: 13, fontWeight: "900", marginBottom: 6 },
  barraBg: { height: 10, borderRadius: 5, backgroundColor: "rgba(255,255,255,0.12)", overflow: "hidden" },
  barraFill: { height: "100%", borderRadius: 5, backgroundColor: Colors.green },
  contador: { color: "rgba(255,255,255,0.7)", fontSize: 12, fontWeight: "800" },

  scroll: { flexGrow: 1, justifyContent: "center", padding: 18 },
  tarjeta: { backgroundColor: Colors.cream, borderRadius: 26, borderWidth: 1, borderColor: Colors.border, padding: 24, alignItems: "center" },
  emoji: { fontSize: 54, marginBottom: 10 },
  titulo: { fontSize: 20, fontWeight: "900", color: Colors.navy, marginBottom: 10, textAlign: "center" },
  contenido: { fontSize: 16, fontWeight: "600", lineHeight: 24, color: "#3B4252", textAlign: "center" },
  dato: { marginTop: 16, width: "100%", backgroundColor: "#FFF1DD", borderRadius: 16, paddingHorizontal: 16, paddingVertical: 12 },
  datoText: { fontSize: 14, fontWeight: "700", color: "#92400E" },

  preguntaBox: { marginTop: 22, width: "100%" },
  preguntaTexto: { fontSize: 15, fontWeight: "900", color: Colors.navy, marginBottom: 12 },
  opcionBase: { borderRadius: 16, borderWidth: 2, paddingHorizontal: 16, paddingVertical: 14, marginBottom: 10 },
  opcion: { borderColor: Colors.border, backgroundColor: Colors.white },
  opcionCorrecta: { borderColor: Colors.green, backgroundColor: "#E9F9EF" },
  opcionMal: { borderColor: "#FCA5A5", backgroundColor: "#FEF2F2" },
  opcionApagada: { borderColor: Colors.border, backgroundColor: Colors.white, opacity: 0.7 },
  opcionText: { fontSize: 15, fontWeight: "700", textAlign: "center" },
  feedback: { marginTop: 4, borderRadius: 16, paddingHorizontal: 16, paddingVertical: 12 },
  feedbackOk: { backgroundColor: "#E9F9EF" },
  feedbackMal: { backgroundColor: "#FEF2F2" },
  feedbackText: { fontSize: 14, fontWeight: "700", lineHeight: 20 },

  preguntarTutor: { marginTop: 18 },
  preguntarTutorText: { color: Colors.blue, fontSize: 13, fontWeight: "800" },

  principal: { borderRadius: 16, paddingVertical: 15, alignItems: "center" },
  principalText: { color: Colors.white, fontSize: 16, fontWeight: "900" },

  // Mini-chat modal
  modalRoot: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  modalSheet: { height: "82%", backgroundColor: Colors.cream, borderTopLeftRadius: 24, borderTopRightRadius: 24, overflow: "hidden" },
  modalHeader: { flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: Colors.navy, paddingHorizontal: 16, paddingBottom: 14 },
  modalTitulo: { color: Colors.white, fontSize: 14, fontWeight: "900" },
  modalSub: { color: "#94A3B8", fontSize: 11, fontWeight: "700" },
  modalHint: { textAlign: "center", marginTop: 24, color: Colors.textLight, fontSize: 14, fontWeight: "600" },
  fila: { flexDirection: "row" },
  filaTutor: { justifyContent: "flex-start" },
  filaMe: { justifyContent: "flex-end" },
  burbuja: { maxWidth: "82%", paddingHorizontal: 16, paddingVertical: 11, borderRadius: 16 },
  burbujaTutor: { backgroundColor: Colors.white, borderTopLeftRadius: 6, borderWidth: 1, borderColor: Colors.border },
  burbujaMe: { backgroundColor: "#E0ECFF", borderTopRightRadius: 6 },
  burbujaText: { fontSize: 14.5, fontWeight: "600", lineHeight: 21 },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: Colors.white, borderTopWidth: 1, borderTopColor: Colors.border, paddingHorizontal: 16, paddingTop: 10 },
  input: { flex: 1, backgroundColor: "#FBF6EF", borderWidth: 2, borderColor: Colors.border, borderRadius: 16, paddingHorizontal: 16, paddingVertical: 11, fontSize: 15, fontWeight: "600", color: Colors.navy },
  enviar: { width: 48, height: 48, borderRadius: 16, backgroundColor: Colors.blue, alignItems: "center", justifyContent: "center" },
  enviarText: { color: Colors.white, fontSize: 20, fontWeight: "900" },
});
