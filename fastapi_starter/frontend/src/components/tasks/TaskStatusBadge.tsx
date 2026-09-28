interface Props {
  status: 'pending' | 'in_progress' | 'completed'
}

const styles: Record<string, string> = {
  pending: 'bg-[var(--text-tertiary)]/10 text-[var(--text-tertiary)]',
  in_progress: 'bg-brand-500/10 text-brand-500',
  completed: 'bg-[var(--color-success)]/10 text-[var(--color-success)]',
}

const labels: Record<string, string> = {
  pending: 'Pending',
  in_progress: 'In progress',
  completed: 'Completed',
}

export default function TaskStatusBadge({ status }: Props) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[status]}`}>
      {labels[status]}
    </span>
  )
}
