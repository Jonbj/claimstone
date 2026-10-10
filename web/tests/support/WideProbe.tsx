import { useWide } from "@/components/wizard/useWide";

function Probe() {
  return <p data-testid="wide">{useWide() ? "wide" : "narrow"}</p>;
}

export default function probe() {
  return <Probe />;
}
