const BASE = '';

/** Fetch the music library as a flat list of album objects */
export async function fetchLibrary() {
  const res = await fetch(`${BASE}/api/library`);
  if (!res.ok) throw new Error('Failed to load library');
  return res.json();
}

/** Start a background download, returns { id, status } */
export async function startDownload(url) {
  const res = await fetch(`${BASE}/api/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) throw new Error('Failed to start download');
  return res.json();
}

/** Subscribe to SSE progress for a job */
export function streamJob(jobId) {
  return new EventSource(`${BASE}/api/download/${jobId}`);
}
