import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[10px] text-[13px] font-medium transition-[background,border-color,color,box-shadow,transform] duration-150 disabled:pointer-events-none disabled:opacity-50 active:translate-y-px [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-ink text-bg hover:bg-ink/90 shadow-[var(--shadow-sm)]",
        accent: "bg-needle text-white hover:bg-needle-ink shadow-[var(--shadow-sm)]",
        secondary: "border border-line bg-surface text-ink hover:border-line-strong hover:bg-surface-2",
        ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
        subtle: "bg-surface-2 text-ink-2 hover:bg-surface-3 hover:text-ink",
        danger: "border border-line bg-surface text-danger hover:bg-danger-soft",
      },
      size: {
        sm: "h-8 px-2.5",
        md: "h-9 px-3.5",
        lg: "h-11 px-5 text-[14px]",
        icon: "size-9",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, ...props }, ref) => {
    const Comp = asChild ? Slot.Root : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
  },
);
Button.displayName = "Button";
