import { useState } from 'react'

const PLACEHOLDER = `A user logs in with username "standard_user" and password "secret_sauce", adds an item to the cart, proceeds to checkout, enters their first name, last name, and zip code, and completes the purchase, verifying the order confirmation message is displayed.`

export default function StoryForm({ onSubmit, busy }) {
  const [story, setStory] = useState('')
  const [url, setUrl] = useState('')

  const canSubmit = story.trim().length > 0 && url.trim().length > 0 && !busy

  function handleSubmit(event) {
    event.preventDefault()
    if (!canSubmit) return
    onSubmit({ story: story.trim(), url: url.trim() })
  }

  return (
    <form className="story-form" onSubmit={handleSubmit}>
      <div className="field">
        <label htmlFor="story">Feature story</label>
        <textarea
          id="story"
          rows={5}
          placeholder={PLACEHOLDER}
          value={story}
          onChange={(event) => setStory(event.target.value)}
          disabled={busy}
        />
        <p className="field__hint">
          Write it like a QA ticket, not a headline — every action and value the flow needs
          (credentials, form fields, pages visited) should be spelled out, since this is the
          only source the scanner has for which pages to visit before generating tests.
        </p>
      </div>

      <div className="field field--url">
        <label htmlFor="url">Target URL</label>
        <input
          id="url"
          type="url"
          placeholder="https://www.saucedemo.com"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          disabled={busy}
        />
      </div>

      <button type="submit" className="btn btn--primary" disabled={!canSubmit}>
        {busy ? 'Generating…' : 'Generate tests'}
      </button>
    </form>
  )
}
