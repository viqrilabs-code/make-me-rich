"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { LoadingState } from "@/components/loading-state";
import { Sidebar } from "@/components/sidebar";
import { TopNav } from "@/components/top-nav";
import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { AgentEvent, AgentStatus, AuthResponse } from "@/types/api";

export function AppShell({
  children,
  mode
}: {
  children: React.ReactNode;
  mode?: string;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const {
    user,
    authResolved,
    hasUser,
    setUser,
    setAuthResolved,
    setBootstrapState,
    setAgentStatus,
    appendAgentEvent,
    setAgentStreamConnected,
    resetAgentState
  } = useAppStore();

  useEffect(() => {
    let cancelled = false;
    apiFetch<AuthResponse>("/api/auth/me")
      .then((response) => {
        if (cancelled) return;
        setUser(response.user);
        setBootstrapState({
          hasUser: response.has_user,
          signupAllowed: response.signup_allowed
        });
      })
      .catch(() => {
        if (cancelled) return;
        setUser(null);
        setBootstrapState({ hasUser: false, signupAllowed: false });
        resetAgentState();
      })
      .finally(() => {
        if (!cancelled) setAuthResolved(true);
      });
    return () => {
      cancelled = true;
    };
  }, [resetAgentState, setAuthResolved, setBootstrapState, setUser]);

  useEffect(() => {
    if (!authResolved || !user || pathname === "/login" || pathname === "/signup") return;

    let cancelled = false;
    const source = new EventSource("/api/agent/stream", { withCredentials: true });

    apiFetch<AgentStatus>("/api/agent/status")
      .then((status) => {
        if (!cancelled) setAgentStatus(status);
      })
      .catch(() => {
        if (!cancelled) setAgentStatus(null);
      });

    source.addEventListener("open", () => {
      if (!cancelled) setAgentStreamConnected(true);
    });

    source.addEventListener("status", (event) => {
      if (cancelled) return;
      const payload = JSON.parse((event as MessageEvent).data) as AgentStatus;
      setAgentStatus(payload);
    });

    source.addEventListener("agent_event", (event) => {
      if (cancelled) return;
      const payload = JSON.parse((event as MessageEvent).data) as AgentEvent;
      appendAgentEvent(payload);
    });

    source.onerror = () => {
      if (!cancelled) setAgentStreamConnected(false);
    };

    return () => {
      cancelled = true;
      setAgentStreamConnected(false);
      source.close();
    };
  }, [
    appendAgentEvent,
    authResolved,
    pathname,
    setAgentStatus,
    setAgentStreamConnected,
    user
  ]);

  useEffect(() => {
    if (!authResolved) return;
    if (!hasUser && pathname !== "/signup") {
      router.replace("/signup");
      return;
    }
    if (hasUser && !user && pathname !== "/login") {
      resetAgentState();
      router.replace("/login");
    }
    if (user && (pathname === "/login" || pathname === "/signup")) {
      router.replace("/");
    }
  }, [authResolved, hasUser, pathname, resetAgentState, router, user]);

  if (!authResolved) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <LoadingState label="Checking your local admin session..." />
      </div>
    );
  }

  if (pathname === "/login" || pathname === "/signup") {
    return <>{children}</>;
  }

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-h-screen min-w-0 flex-1 flex-col">
          <TopNav mode={mode} />
          <main className="flex-1 px-4 py-6 xl:px-8">{children}</main>
        </div>
      </div>
    </div>
  );
}
