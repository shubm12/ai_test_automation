import StatusBadge from './StatusBadge'

function List({ items }) {
  if (!items || items.length === 0) return <p className="test-case__empty">None</p>
  return (
    <ol className="test-case__list">
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ol>
  )
}

export default function TestCaseCard({ index, script, result, onRun }) {
  const { test_case: testCase, file_name: fileName, code } = script
  const status = result?.status ?? 'idle'
  const isRunning = status === 'running'
  const showOutput = (status === 'failed' || status === 'error') && (result?.stdout || result?.stderr)

  return (
    <article className={`test-case test-case--${status}`}>
      <header className="test-case__header">
        <span className="test-case__index">{String(index + 1).padStart(2, '0')}</span>
        <div className="test-case__heading">
          <h3 className="test-case__title">{testCase.title}</h3>
          <p className="test-case__file">{fileName}</p>
        </div>
        <div className="test-case__actions">
          <StatusBadge status={status} />
          <button
            type="button"
            className="btn btn--run"
            onClick={() => onRun(script.script_id)}
            disabled={isRunning}
          >
            {isRunning ? 'Running…' : 'Run'}
          </button>
        </div>
      </header>

      <div className="test-case__grid">
        <section className="test-case__section test-case__section--steps">
          <h4>Steps</h4>
          <List items={testCase.steps} />
        </section>
        <div className="test-case__side">
          <section className="test-case__section">
            <h4>Preconditions</h4>
            <List items={testCase.preconditions} />
          </section>
          <section className="test-case__section">
            <h4>Assertions</h4>
            <List items={testCase.assertions} />
          </section>
          <section className="test-case__section">
            <h4>Edge cases</h4>
            <List items={testCase.edge_cases} />
          </section>
        </div>
      </div>

      <details className="test-case__code">
        <summary>View generated script</summary>
        <pre>
          <code>{code}</code>
        </pre>
      </details>

      {showOutput && (
        <details className="test-case__output" open>
          <summary>{status === 'error' ? 'Execution error' : 'Failure output'}</summary>
          {result.stderr && <pre className="test-case__output-block">{result.stderr}</pre>}
          {result.stdout && (
            <details className="test-case__stdout">
              <summary>stdout</summary>
              <pre className="test-case__output-block">{result.stdout}</pre>
            </details>
          )}
        </details>
      )}
    </article>
  )
}
