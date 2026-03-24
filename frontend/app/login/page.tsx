"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { AppLogo } from "@/components/app-logo";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { AuthResponse } from "@/types/api";

export default function LoginPage() {
  const router = useRouter();
  const { setBootstrapState, setUser } = useAppStore();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch<AuthResponse>("/api/auth/login", {
        method: "POST",
        json: { username, password }
      });
      setUser(response.user);
      setBootstrapState({
        hasUser: response.has_user,
        signupAllowed: response.signup_allowed
      });
      router.replace("/");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to login");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-12">
      <div className="grid w-full max-w-5xl gap-8 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[2rem] border border-border/70 bg-card/85 p-8 shadow-card backdrop-blur">
          <AppLogo size="lg" className="mb-6" />
          <div className="text-xs uppercase tracking-[0.2em] text-primary">Single-user control room</div>
          <h1 className="mt-4 font-display text-5xl font-semibold leading-tight">
            Trade with a seatbelt, not a hype machine.
          </h1>
          <p className="mt-6 max-w-xl text-base text-muted-foreground">
            Advisory mode is the default. The risk engine can veto any AI suggestion. Paper trading works out of the box with the mock broker even before real credentials are configured.
          </p>
          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-border p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Scheduler</div>
              <div className="mt-2 font-display text-2xl">APScheduler</div>
            </div>
            <div className="rounded-2xl border border-border p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Storage</div>
              <div className="mt-2 font-display text-2xl">SQLite</div>
            </div>
            <div className="rounded-2xl border border-border p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Execution</div>
              <div className="mt-2 font-display text-2xl">Advisory / Paper / Live</div>
            </div>
            <div className="rounded-2xl border border-border p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Time display</div>
              <div className="mt-2 font-display text-2xl">Asia/Kolkata</div>
            </div>
          </div>
        </div>
        <Card className="self-center">
          <CardHeader>
            <CardTitle>Admin login</CardTitle>
            <CardDescription>Sign in with the single local account created for this app.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {error ? <ErrorState message={error} /> : null}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid gap-2">
                <Label htmlFor="username">Username</Label>
                <Input id="username" value={username} onChange={(event) => setUsername(event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Signing in..." : "Sign in"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
