"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bot, Gauge, Newspaper, ScrollText, Settings2, ShieldAlert, TrendingUp } from "lucide-react";

import { AppLogo } from "@/components/app-logo";
import { cn } from "@/lib/cn";

const items = [
  { href: "/", label: "Overview", icon: Gauge },
  { href: "/strategy", label: "Strategy", icon: Settings2 },
  { href: "/decisions", label: "Decisions", icon: Bot },
  { href: "/orders", label: "Orders", icon: Activity },
  { href: "/market", label: "Market", icon: TrendingUp },
  { href: "/news", label: "News", icon: Newspaper },
  { href: "/audit", label: "Audit", icon: ScrollText },
  { href: "/safety", label: "Safety", icon: ShieldAlert }
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-72 shrink-0 border-r border-border/70 bg-background/85 px-5 py-6 backdrop-blur xl:block">
      <div className="mb-10">
        <AppLogo size="md" showTagline />
      </div>
      <nav className="space-y-2">
        {items.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
