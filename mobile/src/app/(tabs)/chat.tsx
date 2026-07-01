import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { preguntar, type ChatResponse } from "@/lib/api";
import { Colors } from "@/lib/colors";

/**
 * Asignaturas disponibles para el chat (Fase 1, hardcodeadas — mismo patrón que
 * web/lib/constants.ts). Los `id` deben coincidir con los del backend. Cuando se
 * agregue Comunicación y Lenguaje, basta con añadir { id, nombre } aquí (y en la
 * web). Limitación compartida: aún no hay GET /asignaturas para estudiantes.
 */
const ASIGNATURAS: { id: number; nombre: string }[] = [
  { id: 1, nombre: "Ciencias Naturales" },
];

type Msg = {
  rol: "me" | "tutor";
  texto: string;
  referencias?: ChatResponse["referencias"];
};

export default function ChatScreen() {
  const insets = useSafeAreaInsets();
  const [asignaturaId, setAsignaturaId] = useState<number>(ASIGNATURAS[0].id);
  const [conversacionId, setConversacionId] = useState<number | null>(null);
  const [mensajes, setMensajes] = useState<Msg[]>([]);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    scrollRef.current?.scrollToEnd({ animated: true });
  }, [mensajes, enviando]);

  // Cambiar de asignatura empieza una conversación nueva (contexto distinto).
  function cambiarAsignatura(id: number) {
    if (id === asignaturaId) return;
    setAsignaturaId(id);
    setConversacionId(null);
    setMensajes([]);
  }

  async function enviar() {
    const t = texto.trim();
    if (!t || enviando) return;
    setMensajes((prev) => [...prev, { rol: "me", texto: t }]);
    setTexto("");
    setEnviando(true);
    try {
      const res = await preguntar(t, asignaturaId, conversacionId);
      setConversacionId(res.conversacion_id);
      setMensajes((prev) => [
        ...prev,
        { rol: "tutor", texto: res.respuesta, referencias: res.referencias },
      ]);
    } catch {
      setMensajes((prev) => [
        ...prev,
        { rol: "tutor", texto: "No pude responder ahora. Intenta de nuevo." },
      ]);
    } finally {
      setEnviando(false);
    }
  }

  const asignaturaActual = ASIGNATURAS.find((a) => a.id === asignaturaId);
  const hayVariasAsignaturas = ASIGNATURAS.length > 1;

  return (
    <SafeAreaView style={styles.root} edges={["top"]}>
      {/* Header navy con el Tutor Tigre */}
      <View style={styles.header}>
        <View style={styles.avatar}>
          <Text style={styles.avatarEmoji}>🐯</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.titulo}>Tutor Tigre</Text>
          <View style={styles.enLineaRow}>
            <View style={styles.dot} />
            <Text style={styles.enLinea}>En línea</Text>
          </View>
        </View>
        {mensajes.length > 0 && (
          <Pressable
            onPress={() => {
              setConversacionId(null);
              setMensajes([]);
            }}
            style={styles.nuevo}
            hitSlop={8}
          >
            <Text style={styles.nuevoText}>Nueva</Text>
          </Pressable>
        )}
      </View>

      {/* Selector de asignatura (solo si hay más de una) */}
      {hayVariasAsignaturas ? (
        <View style={styles.asigRow}>
          {ASIGNATURAS.map((a) => {
            const activa = a.id === asignaturaId;
            return (
              <Pressable
                key={a.id}
                onPress={() => cambiarAsignatura(a.id)}
                style={[styles.asigChip, activa && styles.asigChipActiva]}
              >
                <Text style={[styles.asigChipText, activa && styles.asigChipTextActiva]}>
                  {a.nombre}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ) : (
        <View style={styles.asigRow}>
          <View style={styles.asigLabel}>
            <Text style={styles.asigLabelText}>🌱 {asignaturaActual?.nombre}</Text>
          </View>
        </View>
      )}

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={{ padding: 16, gap: 12 }}
        >
          {mensajes.length === 0 && !enviando && (
            <View style={styles.bienvenida}>
              <Text style={styles.bienvenidaEmoji}>🐯</Text>
              <Text style={styles.bienvenidaText}>
                ¡Hola! Soy tu Tutor Tigre. Pregúntame lo que quieras sobre{" "}
                {asignaturaActual?.nombre ?? "tu libro"} y te responderé con la página del libro.
              </Text>
            </View>
          )}

          {mensajes.map((m, i) => {
            const conPagina = (m.referencias ?? []).filter((r) => r.page_num != null);
            return (
              <View key={i} style={[styles.fila, m.rol === "me" ? styles.filaMe : styles.filaTutor]}>
                <View
                  style={[styles.burbuja, m.rol === "me" ? styles.burbujaMe : styles.burbujaTutor]}
                >
                  <Text
                    style={[
                      styles.burbujaText,
                      { color: m.rol === "me" ? "#1E3A8A" : Colors.text },
                    ]}
                  >
                    {m.texto}
                  </Text>
                  {m.rol === "tutor" && conPagina.length > 0 && (
                    <View style={styles.refsRow}>
                      {conPagina.map((r, j) => (
                        <View key={j} style={styles.refChip}>
                          <Text style={styles.refChipText}>📖 Página {r.page_num}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                </View>
              </View>
            );
          })}

          {enviando && (
            <View style={[styles.fila, styles.filaTutor]}>
              <View style={[styles.burbuja, styles.burbujaTutor]}>
                <Text style={[styles.burbujaText, { color: Colors.textLight }]}>
                  El tutor está escribiendo…
                </Text>
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
            {enviando ? (
              <ActivityIndicator color={Colors.white} />
            ) : (
              <Text style={styles.enviarText}>➤</Text>
            )}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.cream },

  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  avatar: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: Colors.navy,
    borderWidth: 3,
    borderColor: Colors.orange,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarEmoji: { fontSize: 24 },
  titulo: { color: Colors.navy, fontSize: 18, fontWeight: "900" },
  enLineaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.green },
  enLinea: { color: Colors.green, fontSize: 12.5, fontWeight: "800" },
  nuevo: {
    backgroundColor: Colors.grayLight,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  nuevoText: { color: Colors.textLight, fontSize: 12.5, fontWeight: "800" },

  asigRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    paddingHorizontal: 16,
    paddingTop: 10,
  },
  asigChip: {
    borderRadius: 12,
    borderWidth: 2,
    borderColor: Colors.border,
    backgroundColor: Colors.white,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  asigChipActiva: { borderColor: Colors.orange, backgroundColor: "#FFF1DD" },
  asigChipText: { color: Colors.textLight, fontSize: 13, fontWeight: "800" },
  asigChipTextActiva: { color: Colors.orangeDark },
  asigLabel: {
    borderRadius: 12,
    borderWidth: 2,
    borderColor: Colors.border,
    backgroundColor: Colors.white,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  asigLabelText: { color: Colors.navy, fontSize: 13, fontWeight: "800" },

  bienvenida: { alignItems: "center", gap: 10, paddingHorizontal: 12, paddingTop: 20 },
  bienvenidaEmoji: { fontSize: 48 },
  bienvenidaText: {
    textAlign: "center",
    color: Colors.text,
    fontSize: 14.5,
    fontWeight: "600",
    lineHeight: 21,
  },

  fila: { flexDirection: "row" },
  filaTutor: { justifyContent: "flex-start" },
  filaMe: { justifyContent: "flex-end" },
  burbuja: { maxWidth: "82%", paddingHorizontal: 16, paddingVertical: 11, borderRadius: 16 },
  burbujaTutor: {
    backgroundColor: Colors.white,
    borderTopLeftRadius: 6,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  burbujaMe: { backgroundColor: "#E0ECFF", borderTopRightRadius: 6 },
  burbujaText: { fontSize: 15, fontWeight: "600", lineHeight: 21 },
  refsRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 8 },
  refChip: {
    backgroundColor: "#FFF1DD",
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  refChipText: { color: "#92400E", fontSize: 11.5, fontWeight: "800" },

  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 16,
    paddingTop: 8,
    backgroundColor: Colors.white,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
  },
  input: {
    flex: 1,
    backgroundColor: Colors.grayLight,
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontSize: 15,
    fontWeight: "600",
    color: Colors.text,
  },
  enviar: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: Colors.blue,
    alignItems: "center",
    justifyContent: "center",
  },
  enviarText: { color: Colors.white, fontSize: 18, fontWeight: "900" },
});
