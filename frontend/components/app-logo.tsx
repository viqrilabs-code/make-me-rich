"use client";

import Image from "next/image";

import { cn } from "@/lib/cn";

type Props = {
  size?: "sm" | "md" | "lg";
  showTagline?: boolean;
  className?: string;
};

const sizes = {
  sm: { width: 168, height: 58 },
  md: { width: 214, height: 74 },
  lg: { width: 300, height: 104 },
};

export function AppLogo({ size = "md", showTagline = false, className }: Props) {
  const dimensions = sizes[size];

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <Image
        src="/logo.png"
        alt="Make Me Rich"
        width={dimensions.width}
        height={dimensions.height}
        priority
        className="h-auto w-auto max-w-full object-contain"
      />
      {showTagline ? (
        <p className="max-w-xs text-sm text-muted-foreground">
          Single-seat market command deck for disciplined risk, live signals, and advisory-first execution.
        </p>
      ) : null}
    </div>
  );
}
