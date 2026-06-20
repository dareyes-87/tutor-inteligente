/**
 * Anillo de progreso circular (conic-gradient), como en el dashboard del diseño.
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
  const deg = (Math.min(100, Math.max(0, pct)) * 3.6).toFixed(1);
  const inner = size - thickness * 2;
  return (
    <div
      className="relative grid place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background: `conic-gradient(${color} ${deg}deg, #ECE7DE 0deg)`,
      }}
    >
      <div
        className="grid place-items-center rounded-full bg-white"
        style={{ width: inner, height: inner }}
      >
        {children}
      </div>
    </div>
  );
}
