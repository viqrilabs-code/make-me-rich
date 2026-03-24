"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

type ChartContainerProps = {
  className?: string;
  children: (size: { width: number; height: number }) => React.ReactNode;
};

export function ChartContainer({ className, children }: ChartContainerProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const updateSize = () => {
      const nextWidth = Math.max(Math.floor(element.clientWidth), 0);
      const nextHeight = Math.max(Math.floor(element.clientHeight), 0);
      setSize((current) =>
        current.width === nextWidth && current.height === nextHeight
          ? current
          : { width: nextWidth, height: nextHeight }
      );
    };

    updateSize();

    const observer = new ResizeObserver(() => updateSize());
    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className={cn("min-h-0 min-w-0 w-full", className)}>
      {size.width > 0 && size.height > 0 ? children(size) : <div className="h-full w-full" />}
    </div>
  );
}
