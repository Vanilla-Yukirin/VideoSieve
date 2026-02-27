import React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "destructive" | "outline" | "success" | "warning";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variants = {
    default: "border-primary/40 bg-primary/20 text-primary",
    secondary: "border-border/90 bg-muted/45 text-muted-foreground",
    destructive: "border-destructive/40 bg-destructive/20 text-destructive",
    outline: "border-border/90 bg-transparent text-foreground",
    success: "border-emerald-400/40 bg-emerald-400/15 text-emerald-300",
    warning: "border-amber-400/40 bg-amber-400/15 text-amber-300",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-ui-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}
