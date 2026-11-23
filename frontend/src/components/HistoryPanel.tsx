import type { HistoryItem } from '../api'
import { formatDuration } from '../utils'

type Props = {
  items: HistoryItem[]
  search: string
  loading: boolean
  onSearch: (value: string) => void
  onReuse: (item: HistoryItem) => void
  onQueue: (item: HistoryItem) => void
}

export function HistoryPanel({
  items,
  search,
  loading,
  onSearch,
  onReuse,
  onQueue,
}: Props) {
  return (
    <aside className="history-panel">
      <div className="history-head">
        <h3>History</h3>
        <input
          type="search"
          placeholder="Search links…"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
        />
      </div>
      {loading && <p className="muted small">Loading…</p>}
      {!loading && !items.length && <p className="muted">No history yet.</p>}
      <ul className="history-list">
        {items.map((item) => (
          <li key={item.id}>
            <button type="button" className="history-item" onClick={() => onReuse(item)}>
              <div className="history-thumb">
                {item.thumbnail_url ? (
                  <img src={item.thumbnail_url} alt="" />
                ) : (
                  <span />
                )}
              </div>
              <div className="history-meta">
                <strong>{item.title || item.video_id}</strong>
                <span className="muted small">
                  {item.channel || '—'} · {formatDuration(item.duration)}
                </span>
                <span className={`badge status-${item.latest_status || 'none'}`}>
                  {item.latest_status || 'previewed'}
                </span>
              </div>
            </button>
            <div className="history-actions">
              <button
                type="button"
                className="history-file"
                onClick={(e) => {
                  e.stopPropagation()
                  onQueue(item)
                }}
              >
                Add to list
              </button>
              {item.latest_status === 'completed' && item.latest_job_id != null && (
                <a
                  className="history-file"
                  href={`/api/downloads/${item.latest_job_id}/file`}
                  onClick={(e) => e.stopPropagation()}
                >
                  Open file
                </a>
              )}
            </div>
          </li>
        ))}
      </ul>
    </aside>
  )
}
