import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { FieldError, messageFor } from "./problems";
import type { FieldProblem } from "@/lib/control";

export interface FieldControlProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
}

/** A label, its control, its help and the server's error for its path. The help and the error sit
 *  outside the label (so the label stays the field's name) and are linked to the control. */
export default function Field(
  { label, help, problems, path, children }:
  {
    label: ReactNode;
    help?: ReactNode;
    problems: FieldProblem[];
    path: string;
    children: (props: FieldControlProps) => ReactNode;
  },
) {
  const base = useId();
  const id = `${base}-c`;
  const helpId = `${base}-h`;
  const errorId = `${base}-e`;
  const invalid = messageFor(problems, path) !== null;
  const describedBy = [help ? helpId : "", invalid ? errorId : ""].filter(Boolean).join(" ");
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      {children({
        id,
        ...(describedBy ? { "aria-describedby": describedBy } : {}),
        ...(invalid ? { "aria-invalid": true as const } : {}),
      })}
      {help ? <p id={helpId} className="text-[13px] text-muted-foreground">{help}</p> : null}
      <FieldError problems={problems} path={path} id={errorId} />
    </div>
  );
}

/** A step's heading: it takes focus when the step appears, so a keyboard or screen-reader user who
 *  has just saved lands on the new step instead of on a button that no longer exists. */
export function StepHeading({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return <h2 ref={ref} tabIndex={-1} className="text-base font-semibold outline-none">{children}</h2>;
}
