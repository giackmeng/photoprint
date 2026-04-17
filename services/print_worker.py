import time
import threading
import subprocess


class PrintWorker:
    def __init__(self, job_manager, image_service, config_service):
        self.job_manager = job_manager
        self.image_service = image_service
        self.config_service = config_service
        self.worker_thread = None

    def start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return

        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def build_lp_command(self, printer_name, processed_path, copies, print_format):
        cmd = [
            "lp",
            "-d", printer_name,
            "-n", str(copies),
            "-o", "ColorModel=RGB",
            "-o", "StpiShrinkOutput=Shrink",
            "-o", "StpLaminate=Glossy",
        ]

        if print_format == "strip":
            cmd += [
                "-o", "PageSize=w288h432-div2",
            ]
        else:
            cmd += [
                "-o", "PageSize=w288h432",
            ]

        cmd.append(processed_path)
        return cmd

    def _extract_printer_job_id(self, stdout):
        if not stdout:
            return None

        for token in stdout.split():
            if "-" in token and "(" not in token:
                return token
        return None

    def _worker_loop(self):
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

                original_path = job.get("original_path")
                processed_path = job.get("processed_path")
                print_format = job.get("print_format", "10x15")
                copies = int(job.get("copies", 1))

                self.image_service.prepare_image(
                    input_path=original_path,
                    output_path=processed_path,
                    print_format=print_format,
                    config=config,
                )

                job = self.job_manager.get_job(job_id)
                if job and job.get("cancelled"):
                    self.job_manager.update_job(
                        job_id,
                        status="error",
                        message="Job annullato",
                        completed_at=time.time(),
                    )
                    self.job_manager.print_queue.task_done()
                    continue

                lp_cmd = self.build_lp_command(
                    printer_name=config["printer_name"],
                    processed_path=processed_path,
                    copies=copies,
                    print_format=print_format,
                )

                result = subprocess.run(
                    lp_cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )

                stdout = (result.stdout or "").strip()
                printer_job_id = self._extract_printer_job_id(stdout)

                self.job_manager.update_job(
                    job_id,
                    status="done",
                    completed_at=time.time(),
                    message=stdout or "Stampa inviata con successo",
                    printer_job_id=printer_job_id,
                )

            except subprocess.CalledProcessError as e:
                err = (e.stderr or e.stdout or "").strip() or "Errore stampa"
                self.job_manager.update_job(
                    job_id,
                    status="error",
                    completed_at=time.time(),
                    message=err,
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