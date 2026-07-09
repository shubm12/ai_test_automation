const LABELS = {
  idle: 'Not run',
  running: 'Running…',
  passed: 'Passed',
  failed: 'Failed',
  error: 'Error',
}

export default function StatusBadge({ status }) {
  return (
    <span className={`badge badge--${status}`}>
      <span className="badge__dot" aria-hidden="true" />
      {LABELS[status] ?? status}
    </span>
  )
}
