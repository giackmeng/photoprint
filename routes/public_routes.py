import os

from flask import render_template, request, jsonify, url_for, make_response, session
from werkzeug.utils import secure_filename


def register_public_routes(
    app,
    paths,
    config_service,
    template_service,
    job_manager,
    image_service,
    device_limit_service,
    device_identity_service,
    print_quota_service,
):
    @app.route("/", methods=["GET"])
    def home():
        config = config_service.load_config()
        max_age_seconds = int(config.get("max_file_age_hours", 24)) * 3600

        image_service.cleanup_old_files(paths.UPLOAD_FOLDER, max_age_seconds)
        image_service.cleanup_old_files(paths.PROCESSED_FOLDER, max_age_seconds)
        image_service.cleanup_old_files(paths.PREVIEW_FOLDER, max_age_seconds)
        job_manager.cleanup_old_jobs(max_age_seconds)

         # 👇 legge event da URL
        event_from_url = request.args.get("event", "").strip()
        if event_from_url:
            session["event_code"] = event_from_url

        event_code = session.get("event_code") or print_quota_service.get_event_code()    
        response = make_response(render_template(
            "index.html",
            config=config,
            event_code=event_code
         ))
        
        device_identity_service.get_or_create_browser_token(request, response)
        return response

    @app.route("/success/<job_id>", methods=["GET"])
    def success(job_id):
        config = config_service.load_config()
        job = job_manager.get_job(job_id)
        return render_template("success.html", config=config, job=job)

    @app.route("/status/<job_id>", methods=["GET"])
    def status(job_id):
        job = job_manager.get_job(job_id)
        if not job:
            return jsonify({"success": False, "message": "Job non trovato"}), 404

        return jsonify({
            "success": True,
            "job_id": job["id"],
            "status": job["status"],
            "message": job["message"],
            "queue_position": job_manager.get_queue_position(job_id),
            "copies": job["copies"],
            "print_format": job["print_format"],
        })

    @app.route("/queue-info", methods=["GET"])
    def queue_info():
        stats = job_manager.build_stats()
        return jsonify({
            "queued": stats["queued"],
            "processing": stats["processing"],
        })

    @app.route("/device-print-limit", methods=["GET"])
    def device_print_limit():
        client_ip, client_mac = device_limit_service.get_client_mac(request)
        browser_token = device_identity_service.get_or_create_browser_token(request)
        event_code = print_quota_service.get_event_code()

        identity_key = device_identity_service.build_identity_key(
            event_code=event_code,
            browser_token=browser_token,
            mac=client_mac,
            ip=client_ip,
        )

        return jsonify({
            "success": True,
            "ip": client_ip,
            "mac": client_mac,
            "event_code": event_code,
            "remaining": print_quota_service.get_remaining(identity_key),
            "limit": print_quota_service.get_default_limit(),
        })

    @app.route("/preview-multiple", methods=["POST"])
    def preview_multiple():
        config = config_service.load_config()

        if "photos" not in request.files:
            return jsonify({"success": False, "message": "Nessun file ricevuto"}), 400

        files = request.files.getlist("photos")
        print_format = request.form.get("print_format", "10x15")

        valid_files = [f for f in files if f and f.filename.strip()]
        if not valid_files:
            return jsonify({"success": False, "message": "Nessuna foto selezionata"}), 400

        if len(valid_files) > 3:
            return jsonify({"success": False, "message": "Puoi usare massimo 3 foto per l'anteprima"}), 400

        if print_format not in ["10x15", "strip"]:
            return jsonify({"success": False, "message": "Formato stampa non valido"}), 400

        temp_paths = []

        try:
            for file in valid_files:
                if not image_service.allowed_file(file.filename):
                    continue

                ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
                temp_path = os.path.join(paths.PREVIEW_FOLDER, image_service.make_unique_filename(ext))
                file.save(temp_path)
                temp_paths.append(temp_path)

            if not temp_paths:
                return jsonify({"success": False, "message": "Nessun file valido per l'anteprima"}), 400

            preview_data = image_service.generate_preview_base64_from_paths(
                temp_paths,
                print_format,
                config
            )

            return jsonify({"success": True, "preview": preview_data})

        except Exception as e:
            return jsonify({"success": False, "message": f"Errore preview: {str(e)}"}), 500

    @app.route("/print-multiple", methods=["POST"])
    def print_multiple():
        config = config_service.load_config()

        if "photos" not in request.files:
            return jsonify({"success": False, "message": "Nessun file ricevuto"}), 400

        files = request.files.getlist("photos")
        copies = request.form.get("copies", "1")
        print_format = request.form.get("print_format", "10x15")

        valid_files = [f for f in files if f and f.filename.strip()]
        if not valid_files:
            return jsonify({"success": False, "message": "Nessuna foto selezionata"}), 400

        if len(valid_files) > 3:
            return jsonify({"success": False, "message": "Puoi inviare massimo 3 foto per volta"}), 400

        try:
            copies = int(copies)
            max_copies = int(config.get("max_copies", 5))
            if copies < 1 or copies > max_copies:
                return jsonify({"success": False, "message": "Numero copie non valido"}), 400
        except ValueError:
            return jsonify({"success": False, "message": "Numero copie non valido"}), 400

        if print_format not in ["10x15", "strip"]:
            return jsonify({"success": False, "message": "Formato stampa non valido"}), 400

        client_ip, client_mac = device_limit_service.get_client_mac(request)
        browser_token = device_identity_service.get_or_create_browser_token(request)
        event_code = session.get("event_code") or print_quota_service.get_event_code()

        identity_key = device_identity_service.build_identity_key(
            event_code=event_code,
            browser_token=browser_token,
            mac=client_mac,
            ip=client_ip,
        )

        try:
            if print_format == "strip":
                allowed, remaining_before = print_quota_service.can_print(identity_key, copies)
                if not allowed:
                    return jsonify({
                        "success": False,
                        "message": f"Limite raggiunto per questo dispositivo. Rimanenti: {remaining_before}"
                    }), 400

                original_paths = []

                for file in valid_files[:3]:
                    if not image_service.allowed_file(file.filename):
                        continue

                    ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
                    original_path = os.path.join(paths.UPLOAD_FOLDER, image_service.make_unique_filename(ext))
                    file.save(original_path)
                    original_paths.append(original_path)

                if not original_paths:
                    return jsonify({"success": False, "message": "Nessun file valido da usare per la strip"}), 400

                processed_path = os.path.join(
                    paths.PROCESSED_FOLDER,
                    image_service.make_unique_filename("jpg")
                )

                job_id = job_manager.create_job(
                    original_path=original_paths[0],
                    original_paths=original_paths,
                    processed_path=processed_path,
                    print_format="strip",
                    copies=copies,
                )

                job_manager.print_queue.put(job_id)

                print_quota_service.register_print(
                    identity_key,
                    copies,
                    meta={
                        "ip": client_ip,
                        "mac": client_mac,
                        "browser_token": browser_token,
                        "event_code": event_code
                    }
                )

                return jsonify({
                    "success": True,
                    "message": f"Strip creata con {len(original_paths)} foto e inviata alla coda di stampa",
                    "job_ids": [job_id],
                    "redirect": url_for("success", job_id=job_id),
                    "remaining_prints": print_quota_service.get_remaining(identity_key),
                    "client_ip": client_ip,
                    "client_mac": client_mac,
                    "event_code": event_code,
                })

            requested_total = len(valid_files) * copies
            allowed, remaining_before = print_quota_service.can_print(identity_key, requested_total)
            if not allowed:
                return jsonify({
                    "success": False,
                    "message": f"Limite raggiunto per questo dispositivo. Rimanenti: {remaining_before}"
                }), 400

            created_jobs = []

            for file in valid_files:
                if not image_service.allowed_file(file.filename):
                    continue

                ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
                original_path = os.path.join(paths.UPLOAD_FOLDER, image_service.make_unique_filename(ext))
                processed_path = os.path.join(paths.PROCESSED_FOLDER, image_service.make_unique_filename("jpg"))

                file.save(original_path)

                job_id = job_manager.create_job(
                    original_path=original_path,
                    original_paths=[original_path],
                    processed_path=processed_path,
                    print_format=print_format,
                    copies=copies,
                )

                job_manager.print_queue.put(job_id)
                created_jobs.append(job_id)

            if not created_jobs:
                return jsonify({"success": False, "message": "Nessun file valido da stampare"}), 400

            print_quota_service.register_print(
                identity_key,
                requested_total,
                meta={
                    "ip": client_ip,
                    "mac": client_mac,
                    "browser_token": browser_token,
                    "event_code": event_code
                }
            )

            return jsonify({
                "success": True,
                "message": f"{len(created_jobs)} foto inviate correttamente alla coda di stampa",
                "job_ids": created_jobs,
                "redirect": url_for("success", job_id=created_jobs[0]),
                "remaining_prints": print_quota_service.get_remaining(identity_key),
                "client_ip": client_ip,
                "client_mac": client_mac,
                "event_code": event_code,
            })

        except Exception as e:
            return jsonify({
                "success": False,
                "message": f"Errore invio multiplo: {str(e)}"
            }), 500


    @app.route("/event-info", methods=["GET"])
    def event_info():
        event_code = session.get("event_code") or print_quota_service.get_event_code()

        return jsonify({
            "success": True,
            "event_code": event_code
        })    

    
    @app.errorhandler(413)
    def too_large(e):
        return jsonify({
            "success": False,
            "message": "File troppo grande. Carica un'immagine sotto i 20 MB."
        }), 413