import * as SliderPrimitive from '@radix-ui/react-slider'
import * as React from 'react'

import { cn } from '@/lib/utils'

function Slider({ className, ...props }: React.ComponentProps<typeof SliderPrimitive.Root>) {
  return (
    <SliderPrimitive.Root
      className={cn('relative flex w-full touch-none select-none items-center py-2', className)}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-muted shadow-[inset_0_1px_1px_rgba(16,36,62,0.08)]">
        <SliderPrimitive.Range className="gradient-primary absolute h-full" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb className="block size-[1.125rem] cursor-grab rounded-full border-2 border-primary bg-card shadow-card-hover transition-[transform,box-shadow] duration-150 hover:scale-110 active:cursor-grabbing focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/20" />
    </SliderPrimitive.Root>
  )
}

export { Slider }
