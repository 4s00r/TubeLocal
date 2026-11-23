type Props = {
  url: string
  loading: boolean
  onChange: (url: string) => void
  onSubmit: () => void
}

export function PasteBar({ url, loading, onChange, onSubmit }: Props) {
  return (
    <form
      className="paste-bar"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }}
    >
      <label className="sr-only" htmlFor="yt-url">
        YouTube URL
      </label>
      <input
        id="yt-url"
        type="url"
        placeholder="Paste YouTube link (watch, youtu.be, m.youtube, shorts…)…"
        value={url}
        onChange={(e) => onChange(e.target.value)}
        autoComplete="off"
        spellCheck={false}
      />
      <button type="submit" disabled={loading || !url.trim()}>
        {loading ? 'Fetching…' : 'Fetch'}
      </button>
    </form>
  )
}
