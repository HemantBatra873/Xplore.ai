export const statusLabels: Record<string, string> = {
  queued: 'Queued',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
}

export const statusColors: Record<string, string> = {
  queued: 'bg-[var(--text-tertiary)]',
  processing: 'bg-brand-500',
  ready: 'bg-[var(--color-success)]',
  failed: 'bg-[var(--color-error)]',
}
