import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Aumenta el límite de body para Server Actions (subida de libros grandes).
  // Nota: las subidas reales van directo al backend (puerto 8000) vía fetch en
  // lib/api.ts, así que este límite no las afecta hoy; se deja para el futuro
  // por si alguna ruta pasa a usar Server Actions.
  experimental: {
    serverActions: {
      bodySizeLimit: "500mb",
    },
  },
};

export default nextConfig;
