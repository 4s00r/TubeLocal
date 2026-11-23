import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  cancelDownload,
  clearDownloadList,
  fetchHistory,
  fetchJobs,
  fetchPreview,
  pauseDownload,
  queueFromHistory,
  removeDownload,
  resumeDownload,
  reuseHistory,
  startDownload,
  subscribeJobEvents,
  type HistoryItem,
  type Job,
  type Preview,
} from './api'
import { DownloadManager } from './components/DownloadManager'
import { HistoryPanel } from './components/HistoryPanel'
import { PasteBar } from './components/PasteBar'
import { PreviewPanel } from './components/PreviewPanel'
import './App.css'

const LIVE_STATUSES = new Set([
  'queued',
  'fetching',
  'downloading',
  'merging',
  'pausing',
])

function App() {
  const [url, setUrl] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [formatId, setFormatId] = useState('bestvideo*+bestaudio/best')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [downloadStarting, setDownloadStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [historySearch, setHistorySearch] = useState('')
  const [historyLoading, setHistoryLoading] = useState(false)
  const unsubscribers = useRef<Map<number, () => void>>(new Map())

  const refreshHistory = useCallback(async (search?: string) => {
    setHistoryLoading(true)
    try {
      const rows = await fetchHistory(search)
      setHistory(rows)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const refreshJobs = useCallback(async () => {
    const rows = await fetchJobs(undefined, 100)
    setJobs(rows)
    return rows
  }, [])

  const upsertJob = useCallback((job: Job) => {
    setJobs((prev) => {
      const idx = prev.findIndex((j) => j.id === job.id)
      if (idx === -1) return [job, ...prev]
      const next = [...prev]
      next[idx] = { ...next[idx], ...job }
      return next
    })
  }, [])

  const watchJob = useCallback(
    (jobId: number) => {
      const existing = unsubscribers.current.get(jobId)
      existing?.()
      unsubscribers.current.delete(jobId)

      const stop = subscribeJobEvents(jobId, (event) => {
        setJobs((prev) => {
          const idx = prev.findIndex((j) => j.id === event.job_id)
          const base =
            idx >= 0
              ? prev[idx]
              : ({
                  id: event.job_id,
                  link_id: 0,
                  format_id: '',
                  status: event.status,
                  progress: 0,
                  created_at: '',
                  updated_at: '',
                } as Job)
          const updated: Job = {
            ...base,
            status: event.status,
            phase: event.phase,
            progress: event.progress ?? base.progress,
            speed: event.speed,
            eta: event.eta,
            speed_bps: event.speed_bps,
            eta_seconds: event.eta_seconds,
            downloaded_bytes: event.downloaded_bytes ?? base.downloaded_bytes,
            total_bytes: event.total_bytes ?? base.total_bytes,
            remaining_bytes: event.remaining_bytes ?? base.remaining_bytes,
            started_at: event.started_at ?? base.started_at,
            ended_at: event.ended_at ?? base.ended_at,
            error: event.error,
            filepath: event.filepath ?? base.filepath,
            filesize: event.filesize ?? base.filesize,
            title: event.title ?? base.title,
            channel: event.channel ?? base.channel,
            thumbnail_url: event.thumbnail_url ?? base.thumbnail_url,
            video_id: event.video_id ?? base.video_id,
            url: event.url ?? base.url,
          }
          if (idx === -1) return [updated, ...prev]
          const next = [...prev]
          next[idx] = updated
          return next
        })
        if (['completed', 'failed', 'cancelled', 'paused'].includes(event.status)) {
          void refreshHistory(historySearch)
          const unsub = unsubscribers.current.get(jobId)
          unsub?.()
          unsubscribers.current.delete(jobId)
        }
      })
      unsubscribers.current.set(jobId, stop)
    },
    [historySearch, refreshHistory],
  )

  useEffect(() => {
    void refreshHistory()
    void (async () => {
      try {
        const rows = await refreshJobs()
        rows.filter((j) => LIVE_STATUSES.has(j.status)).forEach((j) => watchJob(j.id))
      } catch {
        // backend may not be up yet
      }
    })()
    return () => {
      unsubscribers.current.forEach((stop) => stop())
      unsubscribers.current.clear()
    }
  }, [refreshHistory, refreshJobs, watchJob])

  useEffect(() => {
    const t = window.setTimeout(() => {
      void refreshHistory(historySearch || undefined)
    }, 250)
    return () => window.clearTimeout(t)
  }, [historySearch, refreshHistory])

  const handleFetch = async () => {
    setError(null)
    setNotice(null)
    setPreviewLoading(true)
    try {
      const data = await fetchPreview(url)
      setPreview(data)
      setFormatId(data.default_format_id)
      setUrl(data.url)
      await refreshHistory(historySearch || undefined)
    } catch (err) {
      setPreview(null)
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setPreviewLoading(false)
    }
  }

  const enqueueJob = async (job: Job, message: string) => {
    upsertJob(job)
    watchJob(job.id)
    setNotice(message)
    await refreshHistory(historySearch || undefined)
    // Clear paste field so user can add the next video immediately
    setUrl('')
  }

  const handleDownload = async () => {
    if (!preview) return
    setError(null)
    setDownloadStarting(true)
    try {
      const selected = preview.formats.find((f) => f.format_id === formatId)
      const job = await startDownload(preview.url, formatId, selected?.label)
      await enqueueJob(
        {
          ...job,
          title: job.title || preview.title,
          channel: job.channel || preview.channel,
          thumbnail_url: job.thumbnail_url || preview.thumbnail_url,
          video_id: job.video_id || preview.video_id,
          url: job.url || preview.url,
        },
        `Added “${preview.title || preview.video_id}” to download list`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setDownloadStarting(false)
    }
  }

  const handleCancel = async (jobId: number) => {
    try {
      await cancelDownload(jobId)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const handleRemove = async (jobId: number) => {
    try {
      const unsub = unsubscribers.current.get(jobId)
      unsub?.()
      unsubscribers.current.delete(jobId)
      await removeDownload(jobId)
      setJobs((prev) => prev.filter((j) => j.id !== jobId))
      setNotice('Removed from download list')
      await refreshHistory(historySearch || undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const handleClearDone = async () => {
    try {
      const { removed } = await clearDownloadList()
      setJobs((prev) =>
        prev.filter((j) => !['completed', 'failed', 'cancelled'].includes(j.status)),
      )
      setNotice(removed ? `Cleared ${removed} finished download(s)` : 'Nothing to clear')
      await refreshHistory(historySearch || undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const handlePause = async (jobId: number) => {
    try {
      await pauseDownload(jobId)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const handleResume = async (jobId: number) => {
    try {
      const job = await resumeDownload(jobId)
      upsertJob(job)
      watchJob(job.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const handleReuse = async (item: HistoryItem) => {
    setError(null)
    setNotice(null)
    setPreviewLoading(true)
    setUrl(item.url)
    try {
      const data = await reuseHistory(item.id, true)
      setPreview(data)
      setFormatId(data.default_format_id)
      setUrl(data.url)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleQueueFromHistory = async (item: HistoryItem) => {
    setError(null)
    try {
      const job = await queueFromHistory(item.id)
      await enqueueJob(
        job,
        `Queued “${item.title || item.video_id}” from history`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const handleOpenDetails = async (job: Job) => {
    if (!job.link_id) return
    const item = history.find((h) => h.id === job.link_id)
    if (item) {
      await handleReuse(item)
      return
    }
    // Fallback: open by URL
    if (job.url) {
      setUrl(job.url)
      setPreviewLoading(true)
      try {
        const data = await fetchPreview(job.url)
        setPreview(data)
        setFormatId(data.default_format_id)
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setPreviewLoading(false)
      }
    }
  }

  const sortedJobs = useMemo(() => {
    const rank = (status: string) => {
      const order = [
        'downloading',
        'merging',
        'fetching',
        'pausing',
        'queued',
        'paused',
        'completed',
        'failed',
        'cancelled',
      ]
      const i = order.indexOf(status)
      return i === -1 ? 99 : i
    }
    return [...jobs].sort((a, b) => {
      const r = rank(a.status) - rank(b.status)
      if (r !== 0) return r
      return b.id - a.id
    })
  }, [jobs])

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="brand">TubeLocal</p>
          <h1>YouTube Downloader</h1>
          <p className="tagline">
            Multi-download queue · pause/resume each · original quality · public videos only
          </p>
        </div>
      </header>

      <main className="app-main">
        <div className="workspace">
          <PasteBar
            url={url}
            loading={previewLoading}
            onChange={setUrl}
            onSubmit={() => void handleFetch()}
          />
          {error && <div className="banner error">{error}</div>}
          {notice && <div className="banner ok">{notice}</div>}
          {preview && (
            <PreviewPanel
              preview={preview}
              formatId={formatId}
              downloading={downloadStarting}
              onFormatChange={setFormatId}
              onDownload={() => void handleDownload()}
            />
          )}
          <DownloadManager
            jobs={sortedJobs}
            onCancel={(id) => void handleCancel(id)}
            onPause={(id) => void handlePause(id)}
            onResume={(id) => void handleResume(id)}
            onRemove={(id) => void handleRemove(id)}
            onClearDone={() => void handleClearDone()}
            onOpenDetails={(job) => void handleOpenDetails(job)}
          />
        </div>
        <HistoryPanel
          items={history}
          search={historySearch}
          loading={historyLoading}
          onSearch={setHistorySearch}
          onReuse={(item) => void handleReuse(item)}
          onQueue={(item) => void handleQueueFromHistory(item)}
        />
      </main>

      <footer className="app-footer">
        <p className="footer-love">
          Made with love <span className="heart" aria-hidden="true">❤️</span>
        </p>
        <p className="footer-name">4s00r</p>
        <p className="footer-meta muted small">
          TubeLocal · local-only YouTube downloader · public videos · original quality
        </p>
        <p className="footer-meta muted small">
          Downloads stay on your machine · for personal use · not affiliated with YouTube
        </p>
      </footer>
    </div>
  )
}

export default App
