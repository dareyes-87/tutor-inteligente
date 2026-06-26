import { Pressable, StyleSheet, Text, View } from "react-native";

import { ProgressBar } from "@/components/ProgressBar";
import { Colors } from "@/lib/colors";
import type { EstadoLeccion, LeccionEnRuta } from "@/lib/api";

interface EstiloEstado {
  glyph: string;
  circuloBg: string;
  borderColor: string;
  iconBg: string;
  chip: string;
  chipColor: string;
  chipBg: string;
  barColor: string;
  opacity: number;
  textColor: string;
}

function estiloDe(estado: EstadoLeccion): EstiloEstado {
  switch (estado) {
    case "completada":
      return { glyph: "⭐", circuloBg: Colors.green, borderColor: "#BBF7D0", iconBg: "#E9F9EF",
        chip: "Completada", chipColor: "#16A34A", chipBg: "#E9F9EF", barColor: Colors.green, opacity: 1, textColor: Colors.navy };
    case "en_progreso":
      return { glyph: "📖", circuloBg: Colors.orange, borderColor: Colors.orange, iconBg: "#FFF1E7",
        chip: "En progreso", chipColor: "#EA580C", chipBg: "#FFF1E7", barColor: Colors.orange, opacity: 1, textColor: Colors.navy };
    case "disponible":
      return { glyph: "▶️", circuloBg: Colors.blue, borderColor: Colors.blue, iconBg: "#EAF1FF",
        chip: "Disponible", chipColor: Colors.blue, chipBg: "#EAF1FF", barColor: Colors.blue, opacity: 1, textColor: Colors.navy };
    default:
      return { glyph: "🔒", circuloBg: "#E8E4DB", borderColor: "#E8E4DB", iconBg: "#F1EDE5",
        chip: "", chipColor: "", chipBg: "", barColor: Colors.gray, opacity: 0.65, textColor: "#A8A29E" };
  }
}

function Boton({ label, color, shadow, onPress, small }: { label: string; color: string; shadow: string; onPress: () => void; small?: boolean }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [
      styles.boton,
      { backgroundColor: color, shadowColor: shadow, paddingVertical: small ? 9 : 12, transform: [{ translateY: pressed ? 2 : 0 }] },
    ]}>
      <Text style={[styles.botonText, { fontSize: small ? 13 : 14.5 }]}>{label}</Text>
    </Pressable>
  );
}

export function LeccionCard({
  leccion: l,
  onEmpezar,
  onEstudiar,
  onPracticar,
  ocupado,
}: {
  leccion: LeccionEnRuta;
  onEmpezar: (id: number) => void;
  onEstudiar: (id: number) => void;
  onPracticar: (id: number) => void;
  ocupado?: boolean;
}) {
  const s = estiloDe(l.estado);
  const pct = l.actividades_requeridas > 0
    ? Math.round((l.actividades_completadas / l.actividades_requeridas) * 100)
    : 0;
  const mostrarBarra = l.estado === "completada" || l.estado === "en_progreso";

  return (
    <View style={[styles.card, { borderColor: s.borderColor, borderWidth: l.estado === "bloqueada" || l.estado === "completada" ? 1 : 2, opacity: s.opacity }]}>
      <View style={styles.row}>
        <View style={[styles.circulo, { backgroundColor: s.circuloBg }]}>
          <Text style={styles.circuloGlyph}>{s.glyph}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <View style={styles.chipRow}>
            <View style={[styles.chip, { backgroundColor: s.iconBg }]}>
              <Text style={[styles.chipText, { color: s.textColor === Colors.navy ? Colors.textLight : "#A8A29E" }]}>Lección {l.orden}</Text>
            </View>
            {!!s.chip && (
              <View style={[styles.chip, { backgroundColor: s.chipBg }]}>
                <Text style={[styles.chipText, { color: s.chipColor }]}>{s.chip}</Text>
              </View>
            )}
          </View>
          <Text style={[styles.nombre, { color: s.textColor }]} numberOfLines={2}>{l.nombre}</Text>
          <Text style={styles.nivelStars}>
            {l.tiene_corona
              ? "👑 ⭐⭐⭐"
              : "⭐".repeat(l.nivel_completado) + "☆".repeat(3 - l.nivel_completado)}
          </Text>
          {!!l.descripcion && (
            <Text style={[styles.desc, { color: l.estado === "bloqueada" ? "#C4BFB6" : Colors.textLight }]} numberOfLines={2}>
              {l.descripcion}
            </Text>
          )}
          {mostrarBarra && (
            <View style={styles.barRow}>
              <View style={{ flex: 1 }}>
                <ProgressBar progress={pct} color={s.barColor} />
              </View>
              <Text style={[styles.barLabel, { color: s.barColor }]}>
                {l.actividades_completadas}/{l.actividades_requeridas}
              </Text>
            </View>
          )}
        </View>
        {l.estado === "completada" && (
          <View style={styles.puntajeCol}>
            <Text style={styles.puntaje}>{Math.round(l.puntaje_promedio)}</Text>
            <Text style={styles.puntajeLabel}>pts</Text>
          </View>
        )}
      </View>

      {l.estado === "disponible" && (
        <View style={styles.botones}>
          <Boton label={ocupado ? "..." : "Empezar 🚀"} color={Colors.orange} shadow={Colors.orangeDark} onPress={() => onEmpezar(l.id)} />
        </View>
      )}
      {l.estado === "en_progreso" && (
        <View style={styles.botones}>
          <View style={{ flex: 1 }}>
            <Boton label="Estudiar 📖" color={Colors.orange} shadow={Colors.orangeDark} onPress={() => onEstudiar(l.id)} />
          </View>
          <View style={{ flex: 1 }}>
            <Boton label="Practicar 🎯" color={Colors.blue} shadow={Colors.blueDark} onPress={() => onPracticar(l.id)} small />
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.white,
    borderRadius: 22,
    padding: 18,
    marginBottom: 14,
    shadowColor: Colors.navy,
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  row: { flexDirection: "row", alignItems: "center", gap: 14 },
  circulo: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  circuloGlyph: { fontSize: 20 },
  chipRow: { flexDirection: "row", gap: 6, marginBottom: 4 },
  chip: { borderRadius: 999, paddingHorizontal: 9, paddingVertical: 3 },
  chipText: { fontSize: 10.5, fontWeight: "800" },
  nombre: { fontSize: 16, fontWeight: "900", lineHeight: 20 },
  nivelStars: { fontSize: 12, marginTop: 3, letterSpacing: 1 },
  desc: { fontSize: 12.5, fontWeight: "600", marginTop: 2 },
  barRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 9 },
  barLabel: { fontSize: 12, fontWeight: "900" },
  puntajeCol: { alignItems: "center" },
  puntaje: { fontSize: 22, fontWeight: "900", color: Colors.green },
  puntajeLabel: { fontSize: 10.5, fontWeight: "800", color: Colors.textLight },
  botones: { flexDirection: "row", gap: 8, marginTop: 14 },
  boton: { borderRadius: 14, paddingHorizontal: 18, alignItems: "center", justifyContent: "center", shadowOffset: { width: 0, height: 4 }, shadowOpacity: 1, shadowRadius: 0, elevation: 3 },
  botonText: { color: Colors.white, fontWeight: "900" },
});
