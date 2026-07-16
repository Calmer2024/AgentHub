import logoUrl from "../assets/agenthub-logo.png";

type BrandLogoSize = "rail" | "panel" | "mobile" | "empty" | "badge";

const SIZE_CLASS: Record<BrandLogoSize, string> = {
  rail: "agenthub-brand-logo-rail",
  panel: "agenthub-brand-logo-panel",
  mobile: "agenthub-brand-logo-mobile",
  empty: "agenthub-brand-logo-empty",
  badge: "agenthub-brand-logo-badge",
};

export function BrandLogo({
  size = "panel",
  className = "",
  label = "AgentHub",
  decorative = false,
}: {
  size?: BrandLogoSize;
  className?: string;
  label?: string;
  decorative?: boolean;
}) {
  return (
    <span
      className={`agenthub-brand-logo ${SIZE_CLASS[size]} ${className}`.trim()}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : label}
      aria-hidden={decorative ? true : undefined}
    >
      <img src={logoUrl} alt="" draggable={false} />
    </span>
  );
}
