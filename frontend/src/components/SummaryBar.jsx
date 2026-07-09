export default function SummaryBar({ counts, onRunAll, runningAll }) {
  const total = counts.idle + counts.running + counts.passed + counts.failed + counts.error

  return (
    <div className="summary-bar">
      <div className="summary-bar__counts">
        <span className="summary-bar__count">
          <strong>{total}</strong> test case{total === 1 ? '' : 's'}
        </span>
        {counts.passed > 0 && (
          <span className="summary-bar__count summary-bar__count--passed">
            {counts.passed} passed
          </span>
        )}
        {counts.failed > 0 && (
          <span className="summary-bar__count summary-bar__count--failed">
            {counts.failed} failed
          </span>
        )}
        {counts.error > 0 && (
          <span className="summary-bar__count summary-bar__count--error">
            {counts.error} error
          </span>
        )}
        {(counts.idle > 0 || counts.running > 0) && (
          <span className="summary-bar__count summary-bar__count--muted">
            {counts.idle + counts.running} not run
          </span>
        )}
      </div>
      <button
        type="button"
        className="btn btn--secondary"
        onClick={onRunAll}
        disabled={runningAll}
      >
        {runningAll ? 'Running all…' : 'Run all'}
      </button>
    </div>
  )
}
