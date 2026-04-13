import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-blue disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-terracotta text-ivory shadow-[0px_0px_0px_1px_#c96442] hover:bg-terracotta-light rounded-comfortable",
        secondary: "bg-warm-sand text-charcoal-warm shadow-ring-warm hover:shadow-ring-deep rounded-comfortable",
        dark: "bg-dark-surface text-ivory shadow-ring-dark hover:bg-near-black rounded-comfortable",
        outline: "border border-border-cream bg-ivory text-near-black hover:bg-warm-sand rounded-generous",
        ghost: "text-olive-gray hover:bg-warm-sand hover:text-near-black rounded-comfortable",
        link: "text-terracotta underline-offset-4 hover:underline",
        destructive: "bg-error-crimson text-white hover:bg-error-crimson/90 rounded-comfortable",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-10 px-6",
        icon: "h-9 w-9",
        "icon-sm": "h-7 w-7",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  };

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
