/** The Claimstone mark: a slate touchstone with the amber streak the test leaves (brand/logo-mark.svg). */
export default function LogoMark({ size = 28, stone = "#3d4853" }: { size?: number; stone?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Claimstone">
      <path d="M11 26 L37 11 L56 22 L53 47 L19 54 L8 41 Z" fill={stone} stroke={stone} strokeWidth="7" strokeLinejoin="round" />
      <path d="M16 43 L47 25" stroke="#f5a524" strokeWidth="8" strokeLinecap="round" fill="none" />
      <path d="M25 49 L38 41.5" stroke="#f5a524" strokeOpacity=".55" strokeWidth="3" strokeLinecap="round" fill="none" />
    </svg>
  );
}
