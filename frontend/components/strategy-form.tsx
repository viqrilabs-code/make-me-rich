"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { apiFetch } from "@/lib/api";
import type { ConfigResponse } from "@/types/api";

type Props = {
  config: ConfigResponse;
  onSaved: (config: ConfigResponse) => void;
};

export function StrategyForm({ config, onSaved }: Props) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [goalState, setGoalState] = useState({
    initial_capital: config.goal?.initial_capital ?? 100000,
    target_multiplier: config.goal?.target_multiplier ?? 1.2,
    target_days:
      config.goal?.plan?.days_remaining ??
      Math.max(
        1,
        Math.round(
          (new Date(config.goal?.target_date ?? Date.now()).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
        )
      )
  });
  const [strategyState, setStrategyState] = useState({
    polling_interval_minutes: config.strategy?.polling_interval_minutes ?? 5,
    mode: config.strategy?.mode ?? "advisory",
    risk_profile: config.strategy?.risk_profile ?? "balanced",
    max_risk_per_trade_pct: config.strategy?.max_risk_per_trade_pct ?? 1,
    max_daily_loss_pct: config.strategy?.max_daily_loss_pct ?? 2,
    max_drawdown_pct: config.strategy?.max_drawdown_pct ?? 8,
    max_open_positions: config.strategy?.max_open_positions ?? 2,
    max_capital_per_trade_pct: config.strategy?.max_capital_per_trade_pct ?? 20,
    market_hours_only: config.strategy?.market_hours_only ?? true,
    options_enabled: config.strategy?.options_enabled ?? false,
    futures_enabled: config.strategy?.futures_enabled ?? false,
    shorting_enabled: config.strategy?.shorting_enabled ?? false,
    leverage_enabled: config.strategy?.leverage_enabled ?? false,
    mandatory_stop_loss: config.strategy?.mandatory_stop_loss ?? true,
    live_mode_armed: config.strategy?.live_mode_armed ?? false,
    selected_broker: config.strategy?.selected_broker ?? "groww",
    preferred_llm_provider: config.strategy?.preferred_llm_provider ?? "openai",
    watchlist_symbols: (config.strategy?.watchlist_symbols_json ?? ["INFY", "TCS"]).join(", "),
    instrument_types: (config.strategy?.allowed_instruments_json?.instrument_types ?? ["STOCK"]).join(", ")
  });
  const [timezone, setTimezone] = useState(config.user.timezone);
  const [apiKeys, setApiKeys] = useState({
    groww: "",
    growwSecret: "",
    indmoney: "",
    openai: "",
    anthropic: "",
    gemini: "",
    marketaux: ""
  });

  useEffect(() => {
    setTimezone(config.user.timezone);
    setApiKeys({
      groww: "",
      growwSecret: "",
      indmoney: "",
      openai: "",
      anthropic: "",
      gemini: "",
      marketaux: ""
    });
  }, [config.api_credentials, config.user.timezone]);

  const apiCredentialMap = useMemo(
    () => Object.fromEntries(config.api_credentials.map((credential) => [credential.integration, credential])),
    [config.api_credentials]
  );

  const validation = useMemo(() => {
    if (goalState.target_multiplier < 1 || goalState.target_multiplier > 2) {
      return "Target multiplier must stay between 1.0 and 2.0.";
    }
    if (strategyState.mode === "live" && !strategyState.live_mode_armed) {
      return "Live mode requires the explicit arm toggle.";
    }
    return null;
  }, [goalState.target_multiplier, strategyState.live_mode_armed, strategyState.mode]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (validation) {
      setError(validation);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await apiFetch("/api/goals/current", {
        method: "PUT",
        json: {
          initial_capital: goalState.initial_capital,
          target_multiplier: goalState.target_multiplier,
          target_days: goalState.target_days
        }
      });
      await apiFetch("/api/strategy", {
        method: "PUT",
        json: {
          polling_interval_minutes: strategyState.polling_interval_minutes,
          mode: strategyState.mode,
          risk_profile: strategyState.risk_profile,
          max_risk_per_trade_pct: strategyState.max_risk_per_trade_pct,
          max_daily_loss_pct: strategyState.max_daily_loss_pct,
          max_drawdown_pct: strategyState.max_drawdown_pct,
          max_open_positions: strategyState.max_open_positions,
          max_capital_per_trade_pct: strategyState.max_capital_per_trade_pct,
          market_hours_only: strategyState.market_hours_only,
          options_enabled: strategyState.options_enabled,
          futures_enabled: strategyState.futures_enabled,
          shorting_enabled: strategyState.shorting_enabled,
          leverage_enabled: strategyState.leverage_enabled,
          mandatory_stop_loss: strategyState.mandatory_stop_loss,
          live_mode_armed: strategyState.live_mode_armed,
          selected_broker: strategyState.selected_broker,
          preferred_llm_provider: strategyState.preferred_llm_provider,
          watchlist_symbols_json: strategyState.watchlist_symbols
            .split(",")
            .map((item) => item.trim().toUpperCase())
            .filter(Boolean),
          allowed_instruments_json: {
            instrument_types: strategyState.instrument_types
              .split(",")
              .map((item) => item.trim().toUpperCase())
              .filter(Boolean),
            symbols: strategyState.watchlist_symbols
              .split(",")
              .map((item) => item.trim().toUpperCase())
              .filter(Boolean)
          }
        }
      });
      const updated = await apiFetch<ConfigResponse>("/api/config", {
        method: "PUT",
        json: {
          timezone,
          selected_broker: strategyState.selected_broker,
          groww_api_key: apiKeys.groww || undefined,
          groww_api_secret: apiKeys.growwSecret || undefined,
          indmoney_api_key: apiKeys.indmoney || undefined,
          llm_api_key: apiKeys.openai || undefined,
          anthropic_api_key: apiKeys.anthropic || undefined,
          gemini_api_key: apiKeys.gemini || undefined,
          marketaux_api_key: apiKeys.marketaux || undefined
        }
      });
      onSaved(updated);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Goal and cadence</CardTitle>
          <CardDescription>Set the capital target, deadline, and scheduler rhythm.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="initial_capital">Initial capital</Label>
            <Input
              id="initial_capital"
              type="number"
              value={goalState.initial_capital}
              onChange={(event) => setGoalState((state) => ({ ...state, initial_capital: Number(event.target.value) }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="target_multiplier">Target multiplier</Label>
            <Input
              id="target_multiplier"
              type="number"
              step="0.01"
              min={1}
              max={2}
              value={goalState.target_multiplier}
              onChange={(event) => setGoalState((state) => ({ ...state, target_multiplier: Number(event.target.value) }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="target_days">Target deadline in days</Label>
            <Input
              id="target_days"
              type="number"
              min={1}
              value={goalState.target_days}
              onChange={(event) => setGoalState((state) => ({ ...state, target_days: Number(event.target.value) }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="polling_interval">Polling interval in minutes</Label>
            <Input
              id="polling_interval"
              type="number"
              min={1}
              value={strategyState.polling_interval_minutes}
              onChange={(event) =>
                setStrategyState((state) => ({ ...state, polling_interval_minutes: Number(event.target.value) }))
              }
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="timezone">Displayed timezone</Label>
            <Input id="timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)} />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Risk and execution</CardTitle>
          <CardDescription>Safe defaults ship enabled. Live mode stays gated behind arming.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="mode">Mode</Label>
            <Select
              id="mode"
              value={strategyState.mode}
              onChange={(event) =>
                setStrategyState((state) => ({ ...state, mode: event.target.value as "advisory" | "paper" | "live" }))
              }
            >
              <option value="advisory">Advisory</option>
              <option value="paper">Paper</option>
              <option value="live">Live</option>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="risk_profile">Risk profile</Label>
            <Select
              id="risk_profile"
              value={strategyState.risk_profile}
              onChange={(event) => setStrategyState((state) => ({ ...state, risk_profile: event.target.value }))}
            >
              <option value="conservative">Conservative</option>
              <option value="balanced">Balanced</option>
              <option value="assertive">Assertive</option>
            </Select>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label>Max risk per trade %</Label>
              <Input
                type="number"
                step="0.1"
                value={strategyState.max_risk_per_trade_pct}
                onChange={(event) =>
                  setStrategyState((state) => ({ ...state, max_risk_per_trade_pct: Number(event.target.value) }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label>Max daily loss %</Label>
              <Input
                type="number"
                step="0.1"
                value={strategyState.max_daily_loss_pct}
                onChange={(event) =>
                  setStrategyState((state) => ({ ...state, max_daily_loss_pct: Number(event.target.value) }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label>Max drawdown %</Label>
              <Input
                type="number"
                step="0.1"
                value={strategyState.max_drawdown_pct}
                onChange={(event) =>
                  setStrategyState((state) => ({ ...state, max_drawdown_pct: Number(event.target.value) }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label>Max capital per trade %</Label>
              <Input
                type="number"
                step="0.1"
                value={strategyState.max_capital_per_trade_pct}
                onChange={(event) =>
                  setStrategyState((state) => ({ ...state, max_capital_per_trade_pct: Number(event.target.value) }))
                }
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="broker">Selected broker</Label>
            <Select
              id="broker"
              value={strategyState.selected_broker}
              onChange={(event) => setStrategyState((state) => ({ ...state, selected_broker: event.target.value }))}
            >
              {config.broker_credentials.map((broker) => (
                <option key={broker.broker_name} value={broker.broker_name}>
                  {broker.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="preferred_llm_provider">Primary AI provider</Label>
            <Select
              id="preferred_llm_provider"
              value={strategyState.preferred_llm_provider}
              onChange={(event) =>
                setStrategyState((state) => ({
                  ...state,
                  preferred_llm_provider: event.target.value as "openai" | "anthropic" | "gemini"
                }))
              }
            >
              <option value="openai">ChatGPT / OpenAI</option>
              <option value="anthropic">Claude / Anthropic</option>
              <option value="gemini">Google Gemini</option>
            </Select>
            <div className="text-sm text-muted-foreground">
              Fallback order still stays safe and automatic. With the default setting the app tries ChatGPT first, then Claude, then Gemini when those keys are present.
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Watchlist symbols</Label>
            <Input
              value={strategyState.watchlist_symbols}
              onChange={(event) => setStrategyState((state) => ({ ...state, watchlist_symbols: event.target.value }))}
            />
          </div>
          <div className="grid gap-2">
            <Label>Allowed instrument types</Label>
            <Input
              value={strategyState.instrument_types}
              onChange={(event) => setStrategyState((state) => ({ ...state, instrument_types: event.target.value }))}
            />
          </div>
          <div className="grid gap-3 rounded-2xl border border-border p-4">
            {[
              ["Market hours only", "market_hours_only"],
              ["Mandatory stop loss", "mandatory_stop_loss"],
              ["Options enabled", "options_enabled"],
              ["Futures enabled", "futures_enabled"],
              ["Shorting enabled", "shorting_enabled"],
              ["Leverage enabled", "leverage_enabled"],
              ["Live mode armed", "live_mode_armed"]
            ].map(([label, key]) => (
              <div key={key} className="flex items-center justify-between gap-4">
                <span className="text-sm">{label}</span>
                <Switch
                  checked={Boolean(strategyState[key as keyof typeof strategyState])}
                  onCheckedChange={(checked) => setStrategyState((state) => ({ ...state, [key]: checked }))}
                />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card className="xl:col-span-2">
        <CardHeader>
          <CardTitle>API keys and guided setup</CardTitle>
          <CardDescription>
            Paste keys here once and the app will keep using them for both the LLM agent and the ReAct agent. Leave a field blank if you want to keep the currently saved value.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <div className="rounded-2xl border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
            Before the app fetches any trade idea, it checks for the required keys here. If one is missing, the Market
            and best-trade flows will stop and send you back to this section. Groww is the primary live broker path.
            Marketaux is optional because the board can fall back to technical-only analysis when news is unavailable.
            The default provider order is ChatGPT / OpenAI first, Claude second, and Gemini last, and you can also
            choose a different starting provider above.
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <ApiKeyField
              credential={apiCredentialMap.groww}
              value={apiKeys.groww}
              onChange={(value) => setApiKeys((state) => ({ ...state, groww: value }))}
              placeholder="Paste your Groww API key or access token"
            />
            <ApiKeyField
              credential={apiCredentialMap.groww_secret}
              value={apiKeys.growwSecret}
              onChange={(value) => setApiKeys((state) => ({ ...state, growwSecret: value }))}
              placeholder="Paste your Groww API secret"
            />
            <ApiKeyField
              credential={apiCredentialMap.openai}
              value={apiKeys.openai}
              onChange={(value) => setApiKeys((state) => ({ ...state, openai: value }))}
              placeholder="Paste your ChatGPT / OpenAI API key"
            />
            <ApiKeyField
              credential={apiCredentialMap.anthropic}
              value={apiKeys.anthropic}
              onChange={(value) => setApiKeys((state) => ({ ...state, anthropic: value }))}
              placeholder="Paste your Claude / Anthropic API key"
            />
            <ApiKeyField
              credential={apiCredentialMap.gemini}
              value={apiKeys.gemini}
              onChange={(value) => setApiKeys((state) => ({ ...state, gemini: value }))}
              placeholder="Paste your Google Gemini API key"
            />
            <ApiKeyField
              credential={apiCredentialMap.marketaux}
              value={apiKeys.marketaux}
              onChange={(value) => setApiKeys((state) => ({ ...state, marketaux: value }))}
              placeholder="Paste your Marketaux API key"
            />
            <ApiKeyField
              credential={apiCredentialMap.indmoney}
              value={apiKeys.indmoney}
              onChange={(value) => setApiKeys((state) => ({ ...state, indmoney: value }))}
              placeholder="Paste your INDstocks access token only if you still use the legacy broker path"
            />
          </div>

          <div className="rounded-2xl bg-muted/50 p-4 text-sm text-muted-foreground">
            Groww configured: {String(Boolean(config.secret_status.groww_configured))} | Marketaux configured: {String(Boolean(config.secret_status.marketaux_configured))} | OpenAI configured:{" "}
            {String(Boolean(config.secret_status.llm_configured))} | Claude fallback configured:{" "}
            {String(Boolean(config.secret_status.anthropic_configured))} | Gemini fallback configured:{" "}
            {String(Boolean(config.secret_status.gemini_configured))} | Live execution env armed:{" "}
            {String(Boolean(config.secret_status.live_execution_enabled))}
          </div>
        </CardContent>
      </Card>
      <div className="xl:col-span-2 flex items-center justify-between gap-4 rounded-2xl border border-border bg-card/80 p-4">
        <div className="text-sm text-muted-foreground">
          {error ?? validation ?? "All updates are validated client-side before submit."}
        </div>
        <Button type="submit" disabled={saving}>
          {saving ? "Saving..." : "Save settings"}
        </Button>
      </div>
    </form>
  );
}

function ApiKeyField({
  credential,
  value,
  onChange,
  placeholder
}: {
  credential: ConfigResponse["api_credentials"][number] | undefined;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  if (!credential) return null;

  return (
    <div className="rounded-3xl border border-border/70 bg-card/70 p-5 shadow-[0_12px_40px_rgba(15,23,42,0.08)]">
      <div className="flex flex-wrap items-center gap-2">
        <div className="font-semibold">{credential.label}</div>
        <Badge variant={credential.configured ? "success" : "warning"}>
          {credential.configured ? "Configured" : "Required"}
        </Badge>
        <Badge variant="info">
          {credential.source === "strategy"
            ? "Saved in Strategy"
            : credential.source === "environment"
            ? "Loaded from env"
            : "Missing"}
        </Badge>
      </div>

      <p className="mt-3 text-sm leading-6 text-muted-foreground">{credential.description}</p>

      <div className="mt-4 grid gap-2">
        <Label htmlFor={credential.field_name}>{credential.label}</Label>
        <Input
          id={credential.field_name}
          type="password"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={credential.masked_value ? `Current value ${credential.masked_value}` : placeholder}
          autoComplete="off"
        />
        <div className="text-xs text-muted-foreground">
          {credential.masked_value
            ? `Current saved value: ${credential.masked_value}. Leave blank to keep it.`
            : "No saved value yet."}
        </div>
      </div>

      <div className="mt-5 space-y-3">
        <div className="text-xs uppercase tracking-[0.16em] text-primary">How to get it</div>
        <ol className="space-y-2 text-sm leading-6 text-muted-foreground">
          {credential.steps.map((step, index) => (
            <li key={step}>
              <span className="font-semibold text-foreground">{index + 1}. </span>
              {step}
            </li>
          ))}
        </ol>
      </div>

      <div className="mt-4 flex flex-wrap gap-3 text-sm">
        <a href={credential.docs_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
          Read official docs
        </a>
        <a href={credential.manage_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
          Open provider page
        </a>
      </div>
    </div>
  );
}
