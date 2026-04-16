import time
import uuid
import queue
import threading


class JobManager:
    def __init__(self):
        self.jobs = {}
        self.jobs_lock = threading.Lock()
        self.print_queue = queue.Queue()

    def create_job(
        self,
        original_path=None,
        original_paths=None,
        processed_path=None,
        print_format="10x15",
        copies=1,
    ):
        job_id = uuid.uuid4().hex[:12]

        with self.jobs_lock:
            self.jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "created_at": time.time(),
                "started_at": None,
                "completed_at": None,
                "original_path": original_path,
                "original_paths": original_paths or ([] if original_path is None else [original_path]),
                "processed_path": processed_path,
                "print_format": print_format,
                "copies": copies,
                "message": "In coda",
                "printer_job_id": None,
                "cancelled": False,
            }

        return job_id

    def get_job(self, job_id):
        with self.jobs_lock:
            return self.jobs.get(job_id)

    def update_job(self, job_id, **kwargs):
        with self.jobs_lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(kwargs)

    def get_queue_position(self, job_id):
        with self.jobs_lock:
            queued_ids = [jid for jid, data in self.jobs.items() if data["status"] == "queued"]
            queued_ids.sort(key=lambda x: self.jobs[x]["created_at"])
            if job_id in queued_ids:
                return queued_ids.index(job_id) + 1
        return 0

    def ordered_jobs(self, limit=100):
        with self.jobs_lock:
            return sorted(self.jobs.values(), key=lambda j: j["created_at"], reverse=True)[:limit]

    def build_stats(self):
        with self.jobs_lock:
            total = len(self.jobs)
            queued = sum(1 for j in self.jobs.values() if j["status"] == "queued")
            processing = sum(1 for j in self.jobs.values() if j["status"] == "processing")
            done = sum(1 for j in self.jobs.values() if j["status"] == "done")
            errors = sum(1 for j in self.jobs.values() if j["status"] == "error")
            cancelled = sum(1 for j in self.jobs.values() if j.get("cancelled"))
            total_copies = sum(int(j.get("copies", 0)) for j in self.jobs.values() if j["status"] == "done")

        return {
            "total": total,
            "queued": queued,
            "processing": processing,
            "done": done,
            "errors": errors,
            "cancelled": cancelled,
            "total_copies": total_copies,
        }

    def cleanup_old_jobs(self, max_age_seconds):
        now = time.time()
        with self.jobs_lock:
            to_delete = []
            for job_id, job in self.jobs.items():
                ref = job.get("completed_at") or job.get("created_at", now)
                if now - ref > max_age_seconds:
                    to_delete.append(job_id)

            for job_id in to_delete:
                self.jobs.pop(job_id, None)