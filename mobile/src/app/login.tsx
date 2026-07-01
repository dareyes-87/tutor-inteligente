import { useState } from "react";
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

import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Colors } from "@/lib/colors";
import { LogoColegio } from "@/components/LogoColegio";
import { Mascota } from "@/components/Mascota";

export default function LoginScreen() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function handleLogin() {
    if (!username.trim() || !password || enviando) return;
    setEnviando(true);
    setError("");
    try {
      await login(username.trim(), password);
      // El gate de _layout redirige solo al actualizarse el usuario.
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo conectar con el servidor");
      setEnviando(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ flexGrow: 1 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
      {/* Mitad superior crema con logo del colegio + mascota */}
      <View style={styles.top}>
        <LogoColegio size={64} />
        <Mascota size={120} />
        <Text style={styles.titulo}>Tutor Tigre</Text>
        <Text style={styles.subtitulo}>Tu compañero de aprendizaje</Text>
      </View>

      {/* Mitad inferior navy con el formulario */}
      <View style={styles.bottom}>
        <View style={styles.card}>
          <Text style={styles.label}>Usuario</Text>
          <TextInput
            value={username}
            onChangeText={setUsername}
            placeholder="tu usuario"
            placeholderTextColor="#B6BBC6"
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
          />
          <Text style={styles.label}>Contraseña</Text>
          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            placeholderTextColor="#B6BBC6"
            secureTextEntry
            style={styles.input}
          />

          {!!error && <Text style={styles.error}>{error}</Text>}

          <Pressable
            onPress={handleLogin}
            disabled={enviando}
            style={({ pressed }) => [
              styles.boton,
              { opacity: enviando ? 0.7 : 1, transform: [{ translateY: pressed ? 2 : 0 }] },
            ]}
          >
            {enviando ? (
              <ActivityIndicator color={Colors.white} />
            ) : (
              <Text style={styles.botonText}>Iniciar Sesión 🚀</Text>
            )}
          </Pressable>
        </View>
      </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.navy },
  top: { flex: 1, backgroundColor: Colors.cream, alignItems: "center", justifyContent: "center", paddingTop: 40, gap: 6 },
  titulo: { fontSize: 34, fontWeight: "900", color: Colors.navy, marginTop: 8 },
  subtitulo: { fontSize: 15, fontWeight: "700", color: Colors.textLight, marginTop: 4 },
  bottom: { flex: 1, backgroundColor: Colors.navy, justifyContent: "center", paddingHorizontal: 24 },
  card: { backgroundColor: Colors.white, borderRadius: 24, padding: 24, marginTop: -40, shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 20, shadowOffset: { width: 0, height: 10 }, elevation: 8 },
  label: { fontSize: 13, fontWeight: "800", color: "#5A6170", marginBottom: 7, marginTop: 4 },
  input: {
    backgroundColor: "#FBF6EF",
    borderWidth: 2,
    borderColor: Colors.border,
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 15,
    fontWeight: "600",
    color: Colors.navy,
    marginBottom: 14,
  },
  error: { color: Colors.red, fontWeight: "700", fontSize: 13, marginBottom: 10 },
  boton: { backgroundColor: Colors.orange, borderRadius: 18, paddingVertical: 16, alignItems: "center", marginTop: 6 },
  botonText: { color: Colors.white, fontWeight: "900", fontSize: 17 },
});
