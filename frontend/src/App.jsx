import { useEffect, useState } from 'react'
import StoryForm from './components/StoryForm'
import SummaryBar from './components/SummaryBar'
import TestCaseCard from './components/TestCaseCard'
import { executeTest, generateTests } from './api'
import './App.css'

const GENERATION_PHASES = [
  'Resolving the story into a navigable flow…',
  'Scanning the live DOM for real selectors…',
  'Drafting structured test cases…',
  'Generating a grounded Playwright script per test case…',
]

function useTheme() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
  )

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  return [theme, setTheme]
}

export default function App() {
  const [theme, setTheme] = useTheme()
  const [scripts, setScripts] = useState([])
  const [results, setResults] = useState({})
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState(null)
  const [runningAll, setRunningAll] = useState(false)
  const [phase, setPhase] = useState(0)

  useEffect(() => {
    if (!generating) return
    setPhase(0)
    const id = setInterval(() => {
      setPhase((p) => (p + 1) % GENERATION_PHASES.length)
    }, 3200)
    return () => clearInterval(id)
  }, [generating])

  async function handleGenerate({ story, url }) {
    setGenerating(true)
    setGenerateError(null)
    try {
      const data = await generateTests({ story, url })
      setScripts(data.scripts)
      setResults(
        Object.fromEntries(data.scripts.map((s) => [s.script_id, { status: 'idle' }])),
      )
    } catch (err) {
      setGenerateError(err.message)
      setScripts([])
      setResults({})
    } finally {
      setGenerating(false)
    }
  }

  async function runOne(scriptId) {
    setResults((prev) => ({ ...prev, [scriptId]: { status: 'running' } }))
    try {
      const result = await executeTest(scriptId)
      setResults((prev) => ({ ...prev, [scriptId]: result }))
    } catch (err) {
      setResults((prev) => ({
        ...prev,
        [scriptId]: { status: 'error', stderr: err.message },
      }))
    }
  }

  async function handleRunAll() {
    setRunningAll(true)
    for (const script of scripts) {
      await runOne(script.script_id)
    }
    setRunningAll(false)
  }

  const counts = { idle: 0, running: 0, passed: 0, failed: 0, error: 0 }
  for (const script of scripts) {
    const status = results[script.script_id]?.status ?? 'idle'
    counts[status] = (counts[status] ?? 0) + 1
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <p className="eyebrow">Requirements → CodeEngine</p>
          <h1>Story in. Grounded tests out.</h1>
        </div>
        <button
          type="button"
          className="theme-toggle"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          aria-label="Toggle color theme"
        >
          {theme === 'dark' ? '☀' : '☾'}
        </button>
      </header>

      <main className="app-main">
        <StoryForm onSubmit={handleGenerate} busy={generating} />

        {generating && (
          <div className="generating-panel" role="status">
            <span className="spinner" aria-hidden="true" />
            <div>
              <p className="generating-panel__phase">{GENERATION_PHASES[phase]}</p>
              <p className="generating-panel__hint">
                Usually 30–90s — a real browser is being driven and the LLM is called several
                times.
              </p>
            </div>
          </div>
        )}

        {generateError && (
          <div className="error-banner" role="alert">
            <strong>Couldn't generate tests.</strong> {generateError}
          </div>
        )}

        {scripts.length > 0 && (
          <section className="results">
            <SummaryBar counts={counts} onRunAll={handleRunAll} runningAll={runningAll} />
            <div className="test-case-list">
              {scripts.map((script, i) => (
                <TestCaseCard
                  key={script.script_id}
                  index={i}
                  script={script}
                  result={results[script.script_id]}
                  onRun={runOne}
                />
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
