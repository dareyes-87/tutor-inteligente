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
import { useLocalSearchParams, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { obtenerRuta, preguntar, type LeccionEnRuta } from "@/lib/api";
import { Colors } from "@/lib/colors";

const ASIGNATURA_ID = 1;

interface Msg {
  rol: "tutor" | "me";
  texto: string;
}

export default function EstudiarScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const leccionId = Number(id);
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [leccion, setLeccion] = useState<LeccionEnRuta | null>(null);
  const [mensajes, setMensajes] = useState<Msg[]>([]);
  const [conversacionId, setConversacionId] = useState<number | null>(null);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(true);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    let activo = true;
    (async () => {
      try {
        const ruta = await obtenerRuta(1);
        const l = ruta.lecciones.find((x) => x.id === leccionId) ?? null;
        if (!activo) return;
        setLeccion(l);
        const tema = l?.tema_clave || l?.nombre || "esta lección";
        const intro =
          `Preséntate como tutor y da una introducción breve y amigable sobre el tema: ${tema}. ` +
          `Menciona los puntos principales que vamos a aprender.`;
        const res = await preguntar(intro, ASIGNATURA_ID, null);
        if (!activo) return;
        setConversacionId(res.conversacion_id);
        setMensajes([{ rol: "tutor", texto: res.respuesta }]);
      } catch {
        if (activo)
          setMensajes([
            { rol: "tutor", texto: "¡Hola! 🐯 Soy tu tutor. Pregúntame lo que quieras sobre esta lección." },
          ]);
      } finally {
        if (activo) setEnviando(false);
      }
    })();
    return () => {
      activo = false;
    };
  }, [leccionId]);

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
    <View style={styles.root}>
      <StatusBar style="light" />
      {/* Header navy */}
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={() => router.back()} style={styles.x} hitSlop={10}>
          <Text style={styles.xText}>✕</Text>
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitulo} numberOfLines={1}>
            📖 {leccion?.nombre ?? "Lección"}
          </Text>
          <Text style={styles.headerSub}>Tutor Tigre · en línea</Text>
        </View>
        <Pressable
          onPress={() => router.push({ pathname: "/leccion/[id]/practicar", params: { id: String(leccionId) } })}
          style={styles.practicarBtn}
          hitSlop={6}
        >
          <Text style={styles.practicarText}>Practicar 🎯</Text>
        </Pressable>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={0}
      >
        <ScrollView
          ref={scrollRef}
          style={styles.chat}
          contentContainerStyle={{ padding: 16, gap: 14 }}
        >
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

        {/* Input */}
        <View style={[styles.inputRow, { paddingBottom: insets.bottom + 8 }]}>
          <TextInput
            value={texto}
            onChangeText={setTexto}
            placeholder="Escribe tu pregunta…"
            placeholderTextColor="#B6BBC6"
            style={styles.input}
            editable={!enviando || mensajes.length > 0}
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
  root: { flex: 1, backgroundColor: Colors.cream },
  header: { flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: Colors.navy, paddingHorizontal: 16, paddingBottom: 12 },
  x: { width: 34, height: 34, borderRadius: 17, backgroundColor: "rgba(255,255,255,0.12)", alignItems: "center", justifyContent: "center" },
  xText: { color: "rgba(255,255,255,0.85)", fontSize: 16, fontWeight: "900" },
  headerTitulo: { color: Colors.white, fontSize: 15, fontWeight: "900" },
  headerSub: { color: "#94A3B8", fontSize: 11.5, fontWeight: "700" },
  practicarBtn: { backgroundColor: Colors.green, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8 },
  practicarText: { color: Colors.white, fontSize: 12.5, fontWeight: "900" },
  chat: { flex: 1 },
  fila: { flexDirection: "row" },
  filaTutor: { justifyContent: "flex-start" },
  filaMe: { justifyContent: "flex-end" },
  burbuja: { maxWidth: "82%", paddingHorizontal: 16, paddingVertical: 12, borderRadius: 18 },
  burbujaTutor: { backgroundColor: Colors.white, borderTopLeftRadius: 6, borderWidth: 1, borderColor: Colors.border },
  burbujaMe: { backgroundColor: "#E0ECFF", borderTopRightRadius: 6 },
  burbujaText: { fontSize: 15, fontWeight: "600", lineHeight: 21 },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: Colors.white, borderTopWidth: 1, borderTopColor: Colors.border, paddingHorizontal: 16, paddingTop: 10 },
  input: { flex: 1, backgroundColor: "#FBF6EF", borderWidth: 2, borderColor: Colors.border, borderRadius: 18, paddingHorizontal: 18, paddingVertical: 12, fontSize: 15, fontWeight: "600", color: Colors.navy },
  enviar: { width: 50, height: 50, borderRadius: 16, backgroundColor: Colors.blue, alignItems: "center", justifyContent: "center" },
  enviarText: { color: Colors.white, fontSize: 20, fontWeight: "900" },
});
