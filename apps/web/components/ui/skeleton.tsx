import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-comfortable bg-warm-sand", className)}
      {...props}
    />
  );
}

export { Skeleton };
