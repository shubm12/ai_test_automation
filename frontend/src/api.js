const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

async function asJson(response) {
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body?.detail || body?.message
    throw new Error(detail || `Request failed with status ${response.status}`)
  }
  return body
}

export async function generateTests({ story, url }) {
  let response
  try {
    response = await fetch(`${API_BASE}/generate-tests`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ story, url }),
    })
  } catch {
    throw new Error(`Could not reach the backend at ${API_BASE}. Is it running?`)
  }
  return asJson(response)
}

export async function executeTest(scriptId) {
  let response
  try {
    response = await fetch(`${API_BASE}/execute-tests`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script_id: scriptId }),
    })
  } catch {
    throw new Error(`Could not reach the backend at ${API_BASE}. Is it running?`)
  }
  return asJson(response)
}
