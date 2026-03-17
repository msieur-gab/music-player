"""YouTube Music Downloader addon — download playlists as m4a."""

import threading

_ctx = None


def register(ctx):
    """Store server context and return route table."""
    global _ctx
    _ctx = ctx

    return {
        "GET": {
            "/api/downloads": _handle_list_downloads,
            "/api/download/*": _handle_download_sse,
        },
        "POST": {
            "/api/download": _handle_start_download,
        },
    }


def _handle_list_downloads(handler):
    jobs = _ctx["jobs"]
    jobs_lock = _ctx["jobs_lock"]
    with jobs_lock:
        handler._json([{
            "id": j["id"], "url": j["url"],
            "status": j["status"], "done": j["done"],
        } for j in jobs.values()])


def _handle_start_download(handler):
    body = handler._read_body()
    url = body.get("url", "").strip()
    if not url:
        handler._json({"error": "Missing url"}, 400)
        return

    job = _ctx["create_job"](url)
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    handler._json({"id": job["id"], "status": "queued"})


def _handle_download_sse(handler, path):
    job_id = path.split("/")[-1]
    jobs = _ctx["jobs"]
    jobs_lock = _ctx["jobs_lock"]
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        handler._json({"error": "Unknown job"}, 404)
    else:
        handler._stream_sse(job)


def _run_job(job):
    from .downloader import download_playlist

    music_root = _ctx["get_music_root"]()
    job["status"] = "downloading"

    def on_progress(data):
        with job["condition"]:
            job["events"].append(data)
            job["condition"].notify_all()

    try:
        result = download_playlist(job["url"], music_root, on_progress=on_progress)
        result["status"] = "complete"
        with job["condition"]:
            job["events"].append(result)
            job["status"] = "complete"
            job["done"] = True
            job["condition"].notify_all()
    except Exception as e:
        err = {"message": f"Error: {e}", "status": "error"}
        with job["condition"]:
            job["events"].append(err)
            job["status"] = "error"
            job["done"] = True
            job["condition"].notify_all()
