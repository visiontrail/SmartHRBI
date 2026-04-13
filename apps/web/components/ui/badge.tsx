import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-highly border px-2.5 py-0.5 text-label font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-focus-blue focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-terracotta text-ivory",
        secondary: "border-transparent bg-warm-sand text-charcoal-warm",
        outline: "border-border-warm text-olive-gray",
        destructive: "border-transparent bg-error-crimson text-white",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export type BadgeProps = React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof badgeVariants>;

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
