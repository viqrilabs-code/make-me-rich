import { create } from "zustand";

import type { AgentEvent, AgentStatus } from "@/types/api";

type AgentSnapshot = {
  current_equity?: number;
  progress_pct?: number;
  cash_balance?: number;
  margin_available?: number;
  realized_pnl?: number;
  unrealized_pnl?: number;
  today_pnl?: number;
  today_pnl_pct?: number;
  session_pnl?: number;
  session_pnl_pct?: number;
  target_gap?: number;
};

type AuthUser = {
  username: string;
  timezone: string;
} | null;

type AppStore = {
  user: AuthUser;
  authResolved: boolean;
  hasUser: boolean;
  signupAllowed: boolean;
  agentStatus: AgentStatus | null;
  agentEvents: AgentEvent[];
  selectedAgentSymbol: string;
  agentStreamConnected: boolean;
  agentLauncherOpen: boolean;
  setUser: (user: AuthUser) => void;
  setAuthResolved: (value: boolean) => void;
  setBootstrapState: (value: { hasUser: boolean; signupAllowed: boolean }) => void;
  setAgentStatus: (status: AgentStatus | null) => void;
  appendAgentEvent: (event: AgentEvent) => void;
  setSelectedAgentSymbol: (symbol: string) => void;
  setAgentStreamConnected: (value: boolean) => void;
  setAgentLauncherOpen: (value: boolean) => void;
  resetAgentState: () => void;
};

export const useAppStore = create<AppStore>((set) => ({
  user: null,
  authResolved: false,
  hasUser: false,
  signupAllowed: false,
  agentStatus: null,
  agentEvents: [],
  selectedAgentSymbol: "",
  agentStreamConnected: false,
  agentLauncherOpen: false,
  setUser: (user) => set({ user }),
  setAuthResolved: (authResolved) => set({ authResolved }),
  setBootstrapState: ({ hasUser, signupAllowed }) => set({ hasUser, signupAllowed }),
  setAgentStatus: (agentStatus) =>
    set({
      agentStatus,
      agentEvents: agentStatus?.recent_events ?? []
    }),
  appendAgentEvent: (event) =>
    set((state) => {
      const snapshot = (event.metadata_json?.snapshot as AgentSnapshot | undefined) ?? {};
      const agentEvents = [...state.agentEvents, event].slice(-60);
      return {
        agentEvents,
        agentStatus: state.agentStatus
          ? {
              ...state.agentStatus,
              active:
                event.event_type !== "session_stopped" &&
                event.event_type !== "session_failed" &&
                event.event_type !== "target_reached"
                  ? state.agentStatus.active
                  : false,
              can_start:
                event.event_type === "session_stopped" ||
                event.event_type === "session_failed" ||
                event.event_type === "target_reached",
              message: event.message,
              session: state.agentStatus.session
                ? {
                    ...state.agentStatus.session,
                    status:
                      event.event_type === "session_failed"
                        ? "failed"
                        : event.event_type === "target_reached"
                          ? "completed"
                          : event.event_type === "session_stopped"
                            ? "stopped"
                            : state.agentStatus.session.status,
                    current_equity: snapshot.current_equity ?? state.agentStatus.session.current_equity,
                    progress_pct: snapshot.progress_pct ?? state.agentStatus.session.progress_pct,
                    cash_balance: snapshot.cash_balance ?? state.agentStatus.session.cash_balance,
                    margin_available: snapshot.margin_available ?? state.agentStatus.session.margin_available,
                    realized_pnl: snapshot.realized_pnl ?? state.agentStatus.session.realized_pnl,
                    unrealized_pnl: snapshot.unrealized_pnl ?? state.agentStatus.session.unrealized_pnl,
                    today_pnl: snapshot.today_pnl ?? state.agentStatus.session.today_pnl,
                    today_pnl_pct: snapshot.today_pnl_pct ?? state.agentStatus.session.today_pnl_pct,
                    session_pnl: snapshot.session_pnl ?? state.agentStatus.session.session_pnl,
                    session_pnl_pct: snapshot.session_pnl_pct ?? state.agentStatus.session.session_pnl_pct,
                    target_gap: snapshot.target_gap ?? state.agentStatus.session.target_gap,
                    last_message: event.message
                  }
                : state.agentStatus.session,
              recent_events: agentEvents
            }
          : state.agentStatus
      };
    }),
  setSelectedAgentSymbol: (selectedAgentSymbol) => set({ selectedAgentSymbol }),
  setAgentStreamConnected: (agentStreamConnected) => set({ agentStreamConnected }),
  setAgentLauncherOpen: (agentLauncherOpen) => set({ agentLauncherOpen }),
  resetAgentState: () =>
    set({
      agentStatus: null,
      agentEvents: [],
      selectedAgentSymbol: "",
      agentStreamConnected: false,
      agentLauncherOpen: false
    })
}));
