import { AnimatePresence, motion } from 'framer-motion'

export function AnimatedNumber({ value, className }: { value: number; className?: string }) {
  return (
    <span className={className}>
      <AnimatePresence mode="popLayout">
        <motion.span
          key={value}
          initial={{ opacity: 0, y: -6, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 6, scale: 0.95 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="inline-block tabular-nums"
        >
          {value.toLocaleString()}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}
