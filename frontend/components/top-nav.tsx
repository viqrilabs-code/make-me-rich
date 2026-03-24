"use client";

import { Bot, Clock3, Loader2, LogOut, ShieldCheck, Square } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AppLogo } from "@/components/app-logo";
import { ModeBadge } from "@/components/mode-badge";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { AgentCommandResponse, AgentStatus } from "@/types/api";

export function TopNav({ mode }: { mode?: string }) {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const {
    user,
    setUser,
    agentStatus,
    selectedAgentSymbol,
    setAgentStatus,
    setAgentLauncherOpen
  } = useAppStore();

  async function handleLogout() {
    await apiFetch("/api/auth/logout", { method: "POST" });
    setUser(null);
    router.replace("/login");
  }

  async function handleAgentToggle() {
    if (!agentStatus?.active) {
      setAgentLauncherOpen(true);
      router.push("/");
      return;
    }

    setIsSubmitting(true);
    try {
      const symbol = selectedAgentSymbol || agentStatus?.suggested_symbol;
      if (!symbol) return;
      await apiFetch<AgentCommandResponse>("/api/agent/stop", { method: "POST" });
      const refreshedStatus = await apiFetch<AgentStatus>("/api/agent/status");
      setAgentStatus(refreshedStatus);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b border-border/70 bg-background/85 px-4 py-4 backdrop-blur xl:px-8">
      <div className="flex items-center gap-3">
        <ShieldCheck className="h-5 w-5 text-primary" />
        <div>
          <AppLogo size="sm" className="max-w-[170px]" />
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Clock3 className="h-3.5 w-3.5" />
            Asia/Kolkata on screen, UTC under the hood.
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        {mode ? <ModeBadge mode={mode} /> : null}
        <Button
          variant={agentStatus?.active ? "outline" : "default"}
          size="sm"
          onClick={handleAgentToggle}
          disabled={isSubmitting || (!agentStatus?.active && !(selectedAgentSymbol || agentStatus?.suggested_symbol))}
          className="gap-2 rounded-full"
        >
          {isSubmitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : agentStatus?.active ? (
            <Square className="h-4 w-4" />
          ) : (
            <Bot className="h-4 w-4" />
          )}
          {agentStatus?.active ? "Stop AI Agent" : "Open AI Agent"}
        </Button>
        <div className="hidden text-right text-sm text-muted-foreground md:block">
          <div>{user?.username ?? "admin"}</div>
          <div>{user?.timezone ?? "Asia/Kolkata"}</div>
        </div>
        <ThemeToggle />
        <Button variant="ghost" size="sm" onClick={handleLogout} className="rounded-full border border-border/60">
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
