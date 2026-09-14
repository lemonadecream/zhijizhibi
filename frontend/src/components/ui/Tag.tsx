import type { ReactNode } from "react";

export type TagTone = "blue" | "green" | "orange" | "red" | "gray" | "purple";

interface TagProps {
  tone?: TagTone;
  children: ReactNode;
  className?: string;
}

export default function Tag({ tone = "gray", children, className = "" }: TagProps) {
  return <span className={`tag tag--${tone} ${className}`}>{children}</span>;
}
