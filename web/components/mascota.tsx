import Image from "next/image";

/**
 * Imagen de la mascota (tigre). Usa un placeholder en /assets/mascota.png;
 * la imagen real la coloca el equipo en web/public/assets/.
 */
export function Mascota({
  size,
  className,
  alt = "",
}: {
  size: number;
  className?: string;
  alt?: string;
}) {
  return (
    <Image
      src="/assets/mascota.png"
      alt={alt}
      width={size}
      height={size}
      className={className ?? "h-full w-full object-cover"}
    />
  );
}
