import * as React from "react";
import { cn } from "@/lib/utils";

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      className={cn(
        "flex min-h-[60px] w-full rounded-generous border border-border-cream bg-ivory px-3 py-2 text-body-sm text-near-black shadow-ring-border transition-colors",
        "placeholder:text-stone-gray",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-blue focus-visible:border-focus-blue",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Textarea.displayName = "Textarea";

export { Textarea };
