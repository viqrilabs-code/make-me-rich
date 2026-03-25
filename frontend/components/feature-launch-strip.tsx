"use client";

import { Sparkles, WandSparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

type LaunchCard = {
  title: string;
  status: string;
  actionLabel: string;
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  tone: "teal" | "amber";
};

function toneClasses(tone: LaunchCard["tone"]) {
  if (tone === "amber") {
    return {
      shell: "border-amber-400/20 bg-[radial-gradient(circle_at_top_left,_rgba(251,191,36,0.14),_transparent_36%),linear-gradient(150deg,rgba(15,23,42,0.96),rgba(15,23,42,0.84))]",
      badge: "warning" as const,
      button: "bg-amber-400 text-slate-950 hover:bg-amber-300",
      icon: "text-amber-200"
    };
  }
  return {
    shell: "border-primary/20 bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.14),_transparent_36%),linear-gradient(150deg,rgba(15,23,42,0.96),rgba(15,23,42,0.84))]",
    badge: "info" as const,
    button: "bg-primary text-primary-foreground hover:opacity-90",
    icon: "text-cyan-200"
  };
}

export function FeatureLaunchStrip({
  title,
  cards
}: {
  title?: string;
  cards: [LaunchCard, LaunchCard];
}) {
  return (
    <section className="space-y-4">
      {title ? <div className="text-xs uppercase tracking-[0.2em] text-primary">{title}</div> : null}
      <div className="grid gap-4 xl:grid-cols-2">
        {cards.map((card) => {
          const tone = toneClasses(card.tone);
          const Icon = card.tone === "amber" ? Sparkles : WandSparkles;
          return (
            <div
              key={card.title}
              className={cn(
                "rounded-[32px] border p-6 text-white shadow-[0_22px_70px_rgba(15,23,42,0.18)] backdrop-blur",
                tone.shell
              )}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="max-w-xl">
                  <div className="flex items-center gap-2">
                    <Icon className={cn("h-5 w-5", tone.icon)} />
                    <div className="font-display text-3xl font-semibold tracking-tight">{card.title}</div>
                  </div>
                  <div className="mt-3">
                    <Badge variant={tone.badge}>{card.status}</Badge>
                  </div>
                </div>
                <Button
                  type="button"
                  size="lg"
                  className={cn("h-14 rounded-2xl px-6 text-base font-semibold", tone.button)}
                  onClick={card.onClick}
                  disabled={card.disabled || card.loading}
                >
                  {card.loading ? "Working..." : card.actionLabel}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
