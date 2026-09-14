import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "blue" | "green" | "orange" | "red" | "purple";

interface BadgeProps {
  tone?: BadgeTone;
  dot?: boolean;
  children: ReactNode;
}

export default function Badge({ tone = "neutral", dot = false, children }: BadgeProps) {
  return <span className={`badge badge--${tone} ${dot ? "badge--dot" : ""}`}>{children}</span>;
}
