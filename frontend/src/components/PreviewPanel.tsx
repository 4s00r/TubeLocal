import type { FormatInfo, Preview } from '../api'
import { formatDuration } from '../utils'

type Props = {
  preview: Preview
  formatId: string
  downloading: boolean
  onFormatChange: (id: string) => void
  onDownload: () => void
}

export function PreviewPanel({
  preview,
  formatId,
  downloading,
  onFormatChange,
  onDownload,
}: Props) {
  const selected: FormatInfo | undefined = preview.formats.find((f) => f.format_id === formatId)

  return (
    <section className="preview-panel">
      <div className="preview-media">
        {preview.thumbnail_url ? (
          <img src={preview.thumbnail_url} alt="" />
        ) : (
          <div className="thumb-fallback">No thumbnail</div>
        )}
      </div>
      <div className="preview-meta">
        <h2>{preview.title || preview.video_id}</h2>
        <p className="muted">
          {preview.channel || 'Unknown channel'} · {formatDuration(preview.duration)}
          {preview.view_count != null ? ` · ${preview.view_count.toLocaleString()} views` : ''}
        </p>
        {!preview.ffmpeg_available && (
          <p className="warn">
            ffmpeg not found on PATH. Best-quality merge downloads need ffmpeg installed.
          </p>
        )}
        <label className="format-label" htmlFor="format">
          Format
        </label>
        <select
          id="format"
          value={formatId}
          onChange={(e) => onFormatChange(e.target.value)}
        >
          {preview.formats.map((f) => (
            <option key={f.format_id + (f.label || '')} value={f.format_id}>
              {f.label || f.format_id}
              {f.filesize_label ? ` (${f.filesize_label})` : ''}
            </option>
          ))}
        </select>
        {selected?.format_note && <p className="muted small">{selected.format_note}</p>}
        <button
          type="button"
          className="primary"
          onClick={onDownload}
          disabled={downloading}
        >
          {downloading ? 'Adding…' : 'Add to download list'}
        </button>
        <p className="muted small" style={{ marginTop: '0.5rem' }}>
          Keeps other downloads running — add as many as you want.
        </p>
      </div>
    </section>
  )
}
