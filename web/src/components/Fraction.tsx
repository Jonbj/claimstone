// §4.2 rule 1: no zero for an unknown. `null` renders "—" with the not-knowable
// title; a number renders as a fraction. A pending fetch renders `Pending`
// (the parent swaps this component out), never a zero.
export default function Fraction({
  numerator,
  denominator = null,
  title = "not knowable",
}: {
  numerator: number | null;
  denominator?: number | null;
  title?: string;
}) {
  const unknown = numerator === null;
  return (
    <span className={unknown ? "fraction unknown" : "fraction"} title={unknown ? title : undefined}>
      {unknown ? "—" : numerator}
      {!unknown && denominator !== null && <span className="denominator">/{denominator}</span>}
    </span>
  );
}
