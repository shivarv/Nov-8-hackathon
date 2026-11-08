/** Store-shelf price: large dollars, small raised cents ($4⁹⁹). */
export function Price({ cents, className = "" }: { cents: number; className?: string }) {
  const dollars = Math.floor(cents / 100);
  const rest = String(cents % 100).padStart(2, "0");
  return (
    <span className={`price ${className}`} aria-label={`$${dollars}.${rest}`}>
      <span className="price-symbol">$</span>
      {dollars}
      <sup className="price-cents">{rest}</sup>
    </span>
  );
}
