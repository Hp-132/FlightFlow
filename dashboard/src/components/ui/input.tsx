import * as React from 'react'

import { cn } from '@/lib/utils'

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      className={cn(
        'flex h-9 w-full rounded-lg border border-input bg-card px-3 py-1 text-sm text-foreground shadow-xs transition-[border-color,box-shadow] duration-200 placeholder:text-muted-foreground/80 hover:border-secondary/50 focus-visible:border-secondary focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/15 disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}

export { Input }
