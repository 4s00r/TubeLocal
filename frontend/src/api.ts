export type FormatInfo = {
  format_id: string
  ext?: string
  resolution?: string
  fps?: number
  vcodec?: string
  acodec?: string
  filesize?: number
  filesize_label?: string
  kind?: string
  format_note?: string
  label?: string
}

export type Preview = {
  link_id: number
  url: string
  video_id: string
  title?: string
  channel?: string
  duration?: number
  thumbnail_url?: string
  description?: string
  view_count?: number
  formats: FormatInfo[]
  default_format_id: string
  ffmpeg_available: boolean
}

export type Job = {
  id: number
  link_id: number
  format_id: string
  format_note?: string
  status: string
  progress: number
  speed?: string
  eta?: string
  speed_bps?: number
  eta_seconds?: number
  downloaded_bytes?: number
  total_bytes?: number
  remaining_bytes?: number
  phase?: string
  filepath?: string
  filesize?: number
  error?: string
  started_at?: string
  ended_at?: string
  created_at: string
  updated_at: string
  completed_at?: string
  title?: string
  channel?: string
  thumbnail_url?: string
  video_id?: string
  url?: string
  duration?: number
}

export type HistoryItem = {
  id: number
  url: string
  video_id: string
  title?: string
  channel?: string
  duration?: number
  thumbnail_url?: string
  last_preview_at?: string
  created_at: string
  latest_job_id?: number
  latest_status?: string
  latest_progress?: number
  latest_filepath?: string
  latest_format_note?: string
  latest_error?: string
  latest_job_updated_at?: string
}

export type ProgressEvent = {
  job_id: number
  status: string
  phase?: string
  progress?: number
  speed?: string
  eta?: string
  speed_bps?: number
  eta_seconds?: number
  downloaded_bytes?: number
  total_bytes?: number
  remaining_bytes?: number
  started_at?: string
  ended_at?: string
  error?: string
  filepath?: string
  filesize?: number
  title?: string
  channel?: string
  thumbnail_url?: string
  video_id?: string
  url?: string
}

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ')
    }
    return JSON.stringify(data)
  } catch {
    return res.statusText || 'Request failed'
  }
}

export async function fetchPreview(url: string): Promise<Preview> {
  const res = await fetch('/api/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function startDownload(
  url: string,
  format_id: string,
  format_note?: string,
): Promise<Job> {
  const res = await fetch('/api/downloads', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, format_id, format_note }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function cancelDownload(jobId: number): Promise<void> {
  const res = await fetch(`/api/downloads/${jobId}/cancel`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
}

export async function removeDownload(jobId: number): Promise<void> {
  const res = await fetch(`/api/downloads/${jobId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await readError(res))
}

export async function clearDownloadList(
  statuses?: string[],
): Promise<{ removed: number }> {
  const res = await fetch('/api/jobs/clear', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ statuses: statuses ?? null }),
  })
  if (!res.ok) throw new Error(await readError(res))
  const data = await res.json()
  return { removed: data.removed ?? 0 }
}

export async function pauseDownload(jobId: number): Promise<void> {
  const res = await fetch(`/api/downloads/${jobId}/pause`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
}

export async function resumeDownload(jobId: number): Promise<Job> {
  const res = await fetch(`/api/downloads/${jobId}/resume`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function fetchHistory(search?: string): Promise<HistoryItem[]> {
  const qs = search ? `?search=${encodeURIComponent(search)}` : ''
  const res = await fetch(`/api/history${qs}`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function reuseHistory(linkId: number, refresh = true): Promise<Preview> {
  const res = await fetch(`/api/history/${linkId}/reuse?refresh=${refresh}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function fetchActiveJobs(): Promise<Job[]> {
  const res = await fetch('/api/jobs/active')
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function fetchJobs(status?: string, limit = 100): Promise<Job[]> {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  params.set('limit', String(limit))
  const res = await fetch(`/api/jobs?${params}`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function queueFromHistory(
  linkId: number,
  format_id = 'bestvideo*+bestaudio/best',
  format_note?: string,
): Promise<Job> {
  const res = await fetch(`/api/history/${linkId}/queue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ format_id, format_note }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export function subscribeJobEvents(
  jobId: number,
  onEvent: (event: ProgressEvent) => void,
  onError?: (err: Event) => void,
): () => void {
  const es = new EventSource(`/api/downloads/${jobId}/events`)
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as ProgressEvent)
    } catch {
      // ignore malformed
    }
  }
  es.onerror = (err) => {
    onError?.(err)
    es.close()
  }
  return () => es.close()
}
