// Bitrix24: line-art тайл + монограмма «B24» в фирменном циане. Бренд-знак —
// цвет фиксированный (не currentColor), чтобы всегда читался как Bitrix24.
export function Bitrix24Icon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <rect
        x="3"
        y="3"
        width="18"
        height="18"
        rx="5"
        stroke="#159ed9"
        strokeWidth={1.75}
        strokeLinejoin="round"
      />
      <text
        x="12"
        y="12.4"
        textAnchor="middle"
        dominantBaseline="central"
        fill="#159ed9"
        fontFamily="Inter, system-ui, -apple-system, sans-serif"
        fontSize="8.4"
        fontWeight={700}
        letterSpacing="-0.4"
      >
        B24
      </text>
    </svg>
  );
}
