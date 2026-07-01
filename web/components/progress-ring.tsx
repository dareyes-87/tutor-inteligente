/**
 * Anillo de progreso circular dibujado con SVG (arco vía stroke-dasharray).
 * Extremos redondeados (stroke-linecap="round") y escalado responsive: el SVG
 * usa viewBox y w/h al 100%, así que el tamaño lo fija el contenedor; `size`
 * solo define el ancho máximo por defecto.
 */
export function ProgressRing({
  pct,
  color,
  size = 108,
  thickness = 14,
  children,
}: {
  pct: number;
  color: string;
  size?: number;
  thickness?: number;
  children?: React.ReactNode;
}) {
  const valor = Math.min(100, Math.max(0, pct));
  // Coordenadas en el espacio del viewBox (siempre size×size, escala con CSS).
  const radio = (size - thickness) / 2;
  const centro = size / 2;
  const circunferencia = 2 * Math.PI * radio;
  const offset = circunferencia * (1 - valor / 100);

  return (
    <div
      className="relative grid aspect-square w-full place-items-center"
      style={{ maxWidth: size }}
    >
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="h-full w-full -rotate-90"
        aria-hidden="true"
      >
        {/* Pista de fondo */}
        <circle
          cx={centro}
          cy={centro}
          r={radio}
          fill="none"
          stroke="#ECE7DE"
          strokeWidth={thickness}
        />
        {/* Arco de progreso */}
        <circle
          cx={centro}
          cy={centro}
          r={radio}
          fill="none"
          stroke={color}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circunferencia}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset .4s ease" }}
        />
      </svg>
      {/* Texto centrado encima del anillo */}
      <div className="absolute inset-0 grid place-items-center">{children}</div>
    </div>
  );
}
