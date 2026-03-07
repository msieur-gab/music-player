import { startDownload, streamJob } from '../services/api.js';

/**
 * Manages the download form. Supports multiple concurrent downloads,
 * each tracked independently.
 */
export class Downloader {
  constructor(formEl, statusEl, onComplete) {
    this.form = formEl;
    this.status = statusEl;
    this.input = formEl.querySelector('#playlist-url');
    this.button = formEl.querySelector('button');
    this.onComplete = onComplete;
    this.activeJobs = 0;

    this.form.addEventListener('submit', (e) => {
      e.preventDefault();
      const url = this.input.value.trim();
      if (url) {
        this.input.value = '';
        this.start(url);
      }
    });
  }

  async start(url) {
    this.activeJobs++;
    this._addJobLine('Starting…', url);

    try {
      const { id } = await startDownload(url);
      this._followJob(id);
    } catch (err) {
      this._addJobLine(`Failed: ${err.message}`, url);
      this.activeJobs--;
    }
  }

  _followJob(id) {
    const line = this._addJobLine('Connecting…', id);
    const source = streamJob(id);

    source.addEventListener('message', (e) => {
      try {
        const data = JSON.parse(e.data);
        line.textContent = data.message || 'Downloading…';

        if (data.status === 'complete' || data.status === 'error') {
          source.close();
          this.activeJobs--;
          if (data.status === 'complete') {
            line.textContent = `Done: ${data.downloaded}/${data.total} tracks — ${data.artist} - ${data.album}`;
            if (this.onComplete) this.onComplete();
          }
        }
      } catch {
        line.textContent = e.data;
      }
    });

    source.addEventListener('error', () => {
      source.close();
      this.activeJobs--;
      line.textContent = 'Connection lost — check server logs.';
    });
  }

  _addJobLine(text, label) {
    this.status.hidden = false;
    const line = document.createElement('div');
    line.textContent = text;
    this.status.appendChild(line);
    return line;
  }
}
