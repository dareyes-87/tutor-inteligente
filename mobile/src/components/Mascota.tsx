import { Image } from "react-native";

/**
 * Mascota Tutor Tigre (dash.png). Imagen real, reemplaza el emoji 🐯.
 * require relativo a assets para que Metro la resuelva de forma estática.
 */
export function Mascota({ size = 56 }: { size?: number }) {
  return (
    <Image
      source={require("../../assets/images/dash.png")}
      style={{ width: size, height: size }}
      resizeMode="contain"
    />
  );
}
