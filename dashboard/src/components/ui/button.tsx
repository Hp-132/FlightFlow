import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-200 ease-out disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-offset-2 focus-visible:ring-offset-background active:translate-y-0 active:scale-[0.98]",
  {
    variants: {
      variant: {
        // Inset top highlight + a tinted drop gives the gradient a pressed-
        // metal finish instead of looking like a flat fill.
        default:
          'gradient-primary text-primary-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.14),0_1px_2px_rgba(16,36,62,0.24)] hover:-translate-y-px hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_8px_18px_-6px_rgba(24,50,81,0.45)]',
        secondary:
          'bg-secondary text-secondary-foreground shadow-xs hover:-translate-y-px hover:shadow-card-hover',
        outline:
          'border border-border bg-card text-foreground shadow-xs hover:-translate-y-px hover:border-secondary/40 hover:bg-muted/60 hover:shadow-card',
        ghost: 'text-foreground hover:bg-muted',
        destructive:
          'bg-destructive text-destructive-foreground shadow-xs hover:-translate-y-px hover:shadow-card-hover',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-8 rounded-md px-3 text-xs',
        lg: 'h-11 px-6 text-[0.9375rem]',
        icon: 'size-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : 'button'
  return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />
}

export { Button, buttonVariants }
