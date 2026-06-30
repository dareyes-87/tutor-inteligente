import Image from "next/image";

/**
 * Imagen de la mascota (tigre Oasis). La imagen real es /dash.png.
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
      src="/dash.png"
      alt={alt}
      width={size}
      height={size}
      className={className ?? "h-full w-full object-cover"}
    />
  );
}
