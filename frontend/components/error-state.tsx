import { AlertTriangle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ErrorState({ message }: { message: string }) {
  return (
    <Card className="border-rose-500/20">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-rose-600 dark:text-rose-300">
          <AlertTriangle className="h-5 w-5" />
          Something needs attention
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">{message}</CardContent>
    </Card>
  );
}

