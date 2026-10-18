export function formatUtcTime(iso: string | null): string {
  if (!iso) return '--:--'
  const time = new Date(iso).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  })
  return `${time} UTC`
}

export function titleCase(value: string): string {
  return value.charAt(0) + value.slice(1).toLowerCase()
}
