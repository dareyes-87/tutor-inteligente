import { Image } from "react-native";

/**
 * Logo del colegio Oasis Christian School (logo_colegio.png).
 * require relativo a assets para que Metro la resuelva de forma estática.
 */
export function LogoColegio({ size = 64 }: { size?: number }) {
  return (
    <Image
      source={require("../../assets/images/logo_colegio.png")}
      style={{ width: size, height: size }}
      resizeMode="contain"
    />
  );
}
