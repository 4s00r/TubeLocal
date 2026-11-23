import { useMemo, useState } from 'react'
import type { Job } from '../api'
import { elapsedBetween, formatBytes, formatClock, formatHumanDuration } from '../utils'

type Filter = 'all' | 'active' | 'queued' | 'paused' | 'done'

type Props = {
  jobs: Job[]
  onCancel: (jobId: number) => void
  onPause: (jobId: number) => void
  onResume: (jobId: number) => void
  onRemove: (jobId: number) => void
  onClearDone: () => void
  onOpenDetails: (job: Job) => void
}

const ACTIVE = new Set(['fetching', 'downloading', 'merging', 'pausing'])
const QUEUED = new Set(['queued'])
const PAUSED = new Set(['paused'])
const DONE = new Set(['completed', 'failed', 'cancelled'])

function matchesFilter(job: Job, filter: Filter): boolean {
  if (filter === 'all') return true
  if (filter === 'active') return ACTIVE.has(job.status)
  if (filter === 'queued') return QUEUED.has(job.status)
  if (filter === 'paused') return PAUSED.has(job.status)
  return DONE.has(job.status)
}

export function DownloadManager({
  jobs,
  onCancel,
  onPause,
  onResume,
  onRemove,
  onClearDone,
  onOpenDetails,
}: Props) {
  const [filter, setFilter] = useState<Filter>('all')

  const counts = useMemo(() => {
    const c = { all: jobs.length, active: 0, queued: 0, paused: 0, done: 0 }
    for (const j of jobs) {
      if (ACTIVE.has(j.status)) c.active += 1
      else if (QUEUED.has(j.status)) c.queued += 1
      else if (PAUSED.has(j.status)) c.paused += 1
      else if (DONE.has(j.status)) c.done += 1
    }
    return c
  }, [jobs])

  const visible = useMemo(
    () => jobs.filter((j) => matchesFilter(j, filter)),
    [jobs, filter],
  )

  const aggregateSpeed = useMemo(() => {
    const totalBps = jobs
      .filter((j) => ACTIVE.has(j.status) && j.speed_bps)
      .reduce((sum, j) => sum + (j.speed_bps || 0), 0)
    return totalBps > 0
      ? `${(totalBps / (1024 * 1024)).toFixed(2)} MBps combined`
      : null
  }, [jobs])

  return (
    <section className="panel download-manager">
      <div className="dm-header">
        <div>
          <h3>Download list</h3>
          <p className="muted small">
            Queue multiple videos · pause/resume each · like IDM
            {aggregateSpeed ? ` · ${aggregateSpeed}` : ''}
          </p>
        </div>
        <div className="dm-toolbar">
          <div className="dm-filters">
            {(
              [
                ['all', 'All'],
                ['active', 'Active'],
                ['queued', 'Queued'],
                ['paused', 'Paused'],
                ['done', 'Done'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`filter-chip ${filter === key ? 'active' : ''}`}
                onClick={() => setFilter(key)}
              >
                {label} {counts[key]}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="ghost"
            disabled={counts.done === 0}
            onClick={onClearDone}
            title="Remove completed, failed, and cancelled from the list"
          >
            Clear done
          </button>
        </div>
      </div>

      {!visible.length ? (
        <p className="muted">No downloads in this view. Fetch a video and click Add to list.</p>
      ) : (
        <ul className="job-list dm-list">
          {visible.map((job) => {
            const running = ['queued', 'fetching', 'downloading', 'merging'].includes(job.status)
            const canPause = running
            const canResume = job.status === 'paused'
            const canCancel = running || job.status === 'paused' || job.status === 'pausing'
            const total = job.total_bytes ?? job.filesize
            const remaining =
              job.remaining_bytes ??
              (total != null ? Math.max(0, total - (job.downloaded_bytes || 0)) : null)
            const etaLabel =
              job.eta ||
              (job.eta_seconds != null ? formatHumanDuration(job.eta_seconds) : null)

            return (
              <li key={job.id} className="job-item dm-item">
                <button
                  type="button"
                  className="dm-thumb"
                  onClick={() => onOpenDetails(job)}
                  title="Open details from history"
                >
                  {job.thumbnail_url ? (
                    <img src={job.thumbnail_url} alt="" />
                  ) : (
                    <span className="thumb-fallback tiny">YT</span>
                  )}
                </button>

                <div className="dm-body">
                  <div className="job-head">
                    <button
                      type="button"
                      className="dm-title"
                      onClick={() => onOpenDetails(job)}
                    >
                      {job.title || job.video_id || `Job #${job.id}`}
                    </button>
                    <span className={`badge status-${job.status}`}>{job.status}</span>
                  </div>
                  <p className="muted small dm-sub">
                    {job.channel || '—'}
                    {job.format_note ? ` · ${job.format_note}` : ''}
                    {` · #${job.id}`}
                  </p>

                  <div className="progress-track">
                    <div
                      className="progress-fill"
                      style={{
                        width: `${Math.min(100, Math.max(0, job.progress || 0))}%`,
                      }}
                    />
                  </div>

                  <div className="job-stats dm-stats">
                    <span>{(job.progress || 0).toFixed(1)}%</span>
                    <span>Got {formatBytes(job.downloaded_bytes)}</span>
                    <span>Total {formatBytes(total)}</span>
                    <span>Left {formatBytes(remaining)}</span>
                    <span>{job.speed || '—'}</span>
                    <span>ETA {etaLabel || '—'}</span>
                  </div>

                  <div className="job-times muted small">
                    <span>Start {formatClock(job.started_at)}</span>
                    <span>End {formatClock(job.ended_at)}</span>
                    <span>Elapsed {elapsedBetween(job.started_at, job.ended_at)}</span>
                  </div>

                  <div className="job-foot">
                    <div className="job-actions">
                      {canPause && (
                        <button type="button" className="ghost" onClick={() => onPause(job.id)}>
                          Pause
                        </button>
                      )}
                      {canResume && (
                        <button type="button" className="ghost" onClick={() => onResume(job.id)}>
                          Resume
                        </button>
                      )}
                      {canCancel && (
                        <button type="button" className="ghost" onClick={() => onCancel(job.id)}>
                          Cancel
                        </button>
                      )}
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => onOpenDetails(job)}
                      >
                        Details
                      </button>
                      <button
                        type="button"
                        className="ghost danger"
                        onClick={() => onRemove(job.id)}
                        title="Remove from download list (keeps file on disk)"
                      >
                        Remove
                      </button>
                      {job.status === 'completed' && (
                        <a className="link-btn" href={`/api/downloads/${job.id}/file`}>
                          Save file
                        </a>
                      )}
                    </div>
                  </div>
                  {job.error && <p className="error small">{job.error}</p>}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
