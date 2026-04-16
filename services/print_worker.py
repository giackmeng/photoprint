import time
import threading
import subprocess


class PrintWorker:
    def __init__(self, job_manager, image_service, config_service):
        self.job_manager = job_manager
        self.image_service = image_service
        self.config_service = config_service
        self.thread = threading.Thread(target=self.worker, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def worker(self) -> None:
        while True:
            job_id = self.job_manager.print_queue.get()
            config = self.config_service.load_config()

            try:
                job = self.job_manager.get_job(job_id)
                if not job:
                    self.job_manager.print_queue.task_done()
                    continue

                if job.get("cancelled"):
                    self.job_manager.update_job(
                        job_id,
                        status="error",
                        message="Job annullato",
                        completed_at=time.time(),
                    )
                    self.job_manager.print_queue.task_done()
                    continue

                self.job_manager.update_job(
                    job_id,
                    status="processing",
                    started_at=time.time(),
                    message="Preparazione e stampa in corso",
                )

                self.image_service.prepare_image(
                    input_path=job.get("original_path"),
                    output_path=job["processed_path"],
                    print_format=job["print_format"],
                    config=config,
                    input_paths=job.get("original_paths", []),
                )

                result = subprocess.run(
                    [
                        "lp",
                        "-d", config["printer_name"],
                        "-n", str(job["copies"]),
                        job["processed_path"]
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                stdout = result.stdout.strip()
                printer_job_id = None

                if stdout:
                    for token in stdout.split():
                        if "-" in token and "(" not in token:
                            printer_job_id = token
                            break

                self.job_manager.update_job(
                    job_id,
                    status="done",
                    completed_at=time.time(),
                    message=stdout or "Stampa inviata con successo",
                    printer_job_id=printer_job_id,
                )

            except subprocess.CalledProcessError as e:
                self.job_manager.update_job(
                    job_id,
                    status="error",
                    completed_at=time.time(),
                    message=e.stderr.strip() if e.stderr else "Errore stampa",
                )

            except Exception as e:
                self.job_manager.update_job(
                    job_id,
                    status="error",
                    completed_at=time.time(),
                    message=f"Errore: {str(e)}",
                )

            finally:
                self.job_manager.print_queue.task_done()