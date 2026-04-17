import os
import csv
import json
import base64
import socket
import qrcode
from io import BytesIO
from datetime import datetime

from flask import (
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    session,
    send_file,
)
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps


def register_admin_routes(app,
     paths, 
     config_service, 
     template_service, 
     job_manager, 
     image_service, 
     admin_required,
     device_limit_service,
     device_identity_service,
     print_quota_service,

     ):
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        config = config_service.load_config()

        if request.method == "POST":
            password = request.form.get("password", "")
            if password == config.get("admin_password"):
                session["admin_ok"] = True
                return redirect(url_for("admin_dashboard"))
            return render_template("admin_login.html", error="Password non corretta")

        return render_template("admin_login.html", error=None)

    @app.route("/admin/logout", methods=["GET"])
    def admin_logout():
        session.clear()
        return redirect(url_for("admin_login"))

    @app.route("/admin", methods=["GET"])
    def admin_dashboard():
        if not admin_required():
            return redirect(url_for("admin_login"))

        config = config_service.load_config()
        stats = job_manager.build_stats()
        templates_cfg = template_service.load_templates_config()

        templates_10x15 = [t for t in templates_cfg.get("templates", []) if t.get("print_format") == "10x15"]
        templates_strip = [t for t in templates_cfg.get("templates", []) if t.get("print_format") == "strip"]

        return render_template(
            "admin.html",
            config=config,
            jobs=job_manager.ordered_jobs(100),
            stats=stats,
            templates_cfg=templates_cfg,
            templates_10x15=templates_10x15,
            templates_strip=templates_strip,
        )

    @app.route("/admin/jobs", methods=["GET"])
    def admin_jobs():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        data = []
        for job in job_manager.ordered_jobs(100):
            data.append({
                "id": job["id"],
                "status": job["status"],
                "message": job["message"],
                "copies": job["copies"],
                "print_format": job["print_format"],
                "created_at": datetime.fromtimestamp(job["created_at"]).strftime("%d/%m %H:%M:%S"),
                "printer_job_id": job.get("printer_job_id") or "",
                "cancelled": job.get("cancelled", False),
            })

        return jsonify({"success": True, "jobs": data, "stats": job_manager.build_stats()})

    @app.route("/admin/config", methods=["POST"])
    def admin_config():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        data = {
            "wifi_ssid": request.form.get("wifi_ssid", "").strip(),
            "wifi_password": request.form.get("wifi_password", "").strip(),
            "wifi_security": request.form.get("wifi_security", "WPA").strip() or "WPA",
            "printer_name": request.form.get("printer_name", "").strip(),
            "brand_name": request.form.get("brand_name", "").strip(),
            "brand_tagline": request.form.get("brand_tagline", "").strip(),
            "event_name": request.form.get("event_name", "").strip(),
            "event_date": request.form.get("event_date", "").strip(),
            "max_copies": int(request.form.get("max_copies", "5")),
            "max_file_age_hours": int(request.form.get("max_file_age_hours", "24")),
        }

        ok, msg = config_service.validate(data)
        if not ok:
            return jsonify({"success": False, "message": msg}), 400

        config_service.save_config(data)
        app.secret_key = config_service.load_config().get("session_secret", "local-secret")

        return jsonify({"success": True, "message": "Configurazione aggiornata"})

    @app.route("/admin/upload-logo", methods=["POST"])
    def admin_upload_logo():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        if "logo" not in request.files:
            return jsonify({"success": False, "message": "Nessun file ricevuto"}), 400

        logo = request.files["logo"]
        if logo.filename == "":
            return jsonify({"success": False, "message": "Nessun file selezionato"}), 400

        ext = secure_filename(logo.filename).rsplit(".", 1)[-1].lower()
        if ext not in {"png", "jpg", "jpeg", "webp"}:
            return jsonify({"success": False, "message": "Formato logo non supportato"}), 400

        path = os.path.join(paths.ASSETS_FOLDER, "logo.png")
        try:
            with Image.open(logo.stream) as img:
                img = ImageOps.exif_transpose(img).convert("RGBA")
                img.save(path, format="PNG")
            return jsonify({"success": True, "message": "Logo aggiornato"})
        except Exception as e:
            return jsonify({"success": False, "message": f"Errore upload logo: {str(e)}"}), 500

    @app.route("/admin/export", methods=["GET"])
    def admin_export():
        if not admin_required():
            return redirect(url_for("admin_login"))

        export_path = os.path.join(paths.EXPORT_FOLDER, f"jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        ordered_jobs = job_manager.ordered_jobs(10000)

        with open(export_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "job_id", "status", "message", "format", "copies",
                "created_at", "started_at", "completed_at", "printer_job_id", "cancelled"
            ])
            for job in ordered_jobs:
                writer.writerow([
                    job["id"],
                    job["status"],
                    job["message"],
                    job["print_format"],
                    job["copies"],
                    datetime.fromtimestamp(job["created_at"]).strftime("%Y-%m-%d %H:%M:%S") if job["created_at"] else "",
                    datetime.fromtimestamp(job["started_at"]).strftime("%Y-%m-%d %H:%M:%S") if job["started_at"] else "",
                    datetime.fromtimestamp(job["completed_at"]).strftime("%Y-%m-%d %H:%M:%S") if job["completed_at"] else "",
                    job.get("printer_job_id") or "",
                    job.get("cancelled", False),
                ])

        return send_file(export_path, as_attachment=True)

    @app.route("/admin/templates-list", methods=["GET"])
    def admin_templates_list():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        data = template_service.load_templates_config()
        return jsonify({
            "success": True,
            "active_template_10x15": data.get("active_template_10x15"),
            "active_template_strip": data.get("active_template_strip"),
            "templates": data.get("templates", []),
        })

    @app.route("/admin/templates", methods=["POST"])
    def admin_templates():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        active_template_10x15 = request.form.get("active_template_10x15", "").strip() or None
        active_template_strip = request.form.get("active_template_strip", "").strip() or None

        template_service.set_active_templates(
            active_template_10x15=active_template_10x15,
            active_template_strip=active_template_strip,
        )

        return jsonify({"success": True, "message": "Template attivi aggiornati"})

    @app.route("/admin/template-detail/<template_id>", methods=["GET"])
    def admin_template_detail(template_id):
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        tpl = template_service.get_template_by_id(template_id)
        if not tpl:
            return jsonify({"success": False, "message": "Template non trovato"}), 404

        return jsonify({"success": True, "template": tpl})

    @app.route("/admin/template-boxes", methods=["POST"])
    def admin_template_boxes():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        template_id = request.form.get("template_id", "").strip()
        if not template_id:
            return jsonify({"success": False, "message": "Template ID mancante"}), 400

        tpl = template_service.get_template_by_id(template_id)
        if not tpl:
            return jsonify({"success": False, "message": "Template non trovato"}), 404

        try:
            if tpl.get("mode") == "image_template_multi" or tpl.get("print_format") == "strip":
                photo_boxes = [
                    [
                        int(request.form.get("box1_x", "0")),
                        int(request.form.get("box1_y", "0")),
                        int(request.form.get("box1_w", "0")),
                        int(request.form.get("box1_h", "0")),
                    ],
                    [
                        int(request.form.get("box2_x", "0")),
                        int(request.form.get("box2_y", "0")),
                        int(request.form.get("box2_w", "0")),
                        int(request.form.get("box2_h", "0")),
                    ],
                    [
                        int(request.form.get("box3_x", "0")),
                        int(request.form.get("box3_y", "0")),
                        int(request.form.get("box3_w", "0")),
                        int(request.form.get("box3_h", "0")),
                    ],
                ]

                for box in photo_boxes:
                    if box[2] <= 0 or box[3] <= 0:
                        return jsonify({"success": False, "message": "Larghezza e altezza devono essere maggiori di zero"}), 400

                updated = template_service.update_template_boxes(
                    template_id=template_id,
                    photo_boxes=photo_boxes,
                    photo_fit=request.form.get("photo_fit", "").strip(),
                )
            else:
                photo_box = [
                    int(request.form.get("photo_x", "0")),
                    int(request.form.get("photo_y", "0")),
                    int(request.form.get("photo_w", "0")),
                    int(request.form.get("photo_h", "0")),
                ]

                if photo_box[2] <= 0 or photo_box[3] <= 0:
                    return jsonify({"success": False, "message": "Larghezza e altezza devono essere maggiori di zero"}), 400

                updated = template_service.update_template_boxes(
                    template_id=template_id,
                    photo_box=photo_box,
                    photo_fit=request.form.get("photo_fit", "").strip(),
                )

            return jsonify({"success": True, "message": "Box foto aggiornati con successo", "template": updated})

        except ValueError:
            return jsonify({"success": False, "message": "Valori box non validi"}), 400
        except Exception as e:
            return jsonify({"success": False, "message": f"Errore aggiornamento box: {str(e)}"}), 500

    @app.route("/admin/upload-template", methods=["POST"])
    def admin_upload_template():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        if "template_file" not in request.files:
            return jsonify({"success": False, "message": "Nessun file template ricevuto"}), 400

        template_file = request.files["template_file"]
        if template_file.filename == "":
            return jsonify({"success": False, "message": "Nessun file selezionato"}), 400

        ext = secure_filename(template_file.filename).rsplit(".", 1)[-1].lower()
        if ext not in {"png", "jpg", "jpeg", "webp"}:
            return jsonify({"success": False, "message": "Formato template non supportato"}), 400

        template_id = request.form.get("template_id", "").strip()
        label = request.form.get("label", "").strip()
        print_format = request.form.get("print_format", "").strip()
        mode = request.form.get("mode", "").strip()

        if not template_id:
            return jsonify({"success": False, "message": "template_id obbligatorio"}), 400
        if not label:
            return jsonify({"success": False, "message": "label obbligatoria"}), 400
        if print_format not in {"10x15", "strip"}:
            return jsonify({"success": False, "message": "Formato stampa non valido"}), 400
        if mode not in {"image_template", "image_template_multi"}:
            return jsonify({"success": False, "message": "Mode non valido"}), 400

        filename = f"{template_id}.{ext}"
        save_path = os.path.join(paths.ASSETS_FOLDER, filename)

        try:
            with Image.open(template_file.stream) as img:
                img = ImageOps.exif_transpose(img)
                expected_size = (1200, 1800) if print_format == "10x15" else (600, 1800)

                if img.size != expected_size:
                    return jsonify({
                        "success": False,
                        "message": f"Dimensione non valida. Atteso {expected_size[0]}x{expected_size[1]} px, trovato {img.size[0]}x{img.size[1]} px"
                    }), 400

                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")

                if ext == "png":
                    img.save(save_path, format="PNG")
                elif ext in {"jpg", "jpeg"}:
                    img.convert("RGB").save(save_path, format="JPEG", quality=95)
                elif ext == "webp":
                    img.save(save_path, format="WEBP", quality=95)

            if print_format == "10x15":
                tpl = template_service.build_single_image_template(
                    template_id=template_id,
                    label=label,
                    print_format="10x15",
                    template_file=filename,
                    photo_box=[110, 120, 980, 1280],
                    photo_fit="cover",
                    rotate_landscape=True,
                )
            else:
                tpl = template_service.build_multi_image_template(
                    template_id=template_id,
                    label=label,
                    print_format="strip",
                    template_file=filename,
                    photo_boxes=[
                        [30, 250, 540, 450],
                        [30, 724, 540, 450],
                        [30, 1198, 540, 450],
                    ],
                    photo_fit="cover",
                )

            template_service.upsert_template(tpl)

            return jsonify({
                "success": True,
                "message": f"Template '{label}' caricato correttamente",
                "template_id": template_id,
                "template_file": filename,
            })

        except Exception as e:
            return jsonify({"success": False, "message": f"Errore lettura template: {str(e)}"}), 500

    @app.route("/admin/reprint/<job_id>", methods=["POST"])
    def admin_reprint(job_id):
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        src_job = job_manager.get_job(job_id)
        if not src_job or not os.path.exists(src_job.get("original_path", "")):
            return jsonify({"success": False, "message": "Job non disponibile"}), 404

        new_job_id = job_manager.create_job(
            original_path=src_job.get("original_path"),
            original_paths=src_job.get("original_paths", [src_job.get("original_path")]),
            processed_path=os.path.join(paths.PROCESSED_FOLDER, image_service.make_unique_filename("jpg")),
            print_format=src_job["print_format"],
            copies=src_job["copies"],
        )

        job_manager.print_queue.put(new_job_id)
        return jsonify({"success": True, "message": "Ristampa aggiunta in coda"})

    @app.route("/admin/reprint-last", methods=["POST"])
    def admin_reprint_last():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        done_jobs = [
            j for j in job_manager.ordered_jobs(1000)
            if j["status"] == "done" and os.path.exists(j.get("original_path", ""))
        ]

        if not done_jobs:
            return jsonify({"success": False, "message": "Nessun job completato disponibile"}), 404

        src_job = done_jobs[0]
        new_job_id = job_manager.create_job(
            original_path=src_job.get("original_path"),
            original_paths=src_job.get("original_paths", [src_job.get("original_path")]),
            processed_path=os.path.join(paths.PROCESSED_FOLDER, image_service.make_unique_filename("jpg")),
            print_format=src_job["print_format"],
            copies=src_job["copies"],
        )

        job_manager.print_queue.put(new_job_id)
        return jsonify({"success": True, "message": "Ristampa ultimo job aggiunta in coda"})


    @app.route("/admin/cancel/<job_id>", methods=["POST"])
    def admin_cancel(job_id):
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        job = job_manager.get_job(job_id)
        if not job:
            return jsonify({"success": False, "message": "Job non trovato"}), 404

        if job["status"] != "queued":
            return jsonify({"success": False, "message": "Puoi annullare solo job in coda"}), 400

        job_manager.update_job(
            job_id,
            cancelled=True,
            status="error",
            message="Job annullato manualmente",
            completed_at=datetime.now().timestamp(),
        )

        return jsonify({"success": True, "message": "Job annullato"})

    @app.route("/admin/cleanup", methods=["POST"])
    def admin_cleanup():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        config = config_service.load_config()
        max_age_seconds = int(config.get("max_file_age_hours", 24)) * 3600

        image_service.cleanup_old_files(paths.UPLOAD_FOLDER, max_age_seconds)
        image_service.cleanup_old_files(paths.PROCESSED_FOLDER, max_age_seconds)
        image_service.cleanup_old_files(paths.PREVIEW_FOLDER, max_age_seconds)
        job_manager.cleanup_old_jobs(max_age_seconds)

        return jsonify({"success": True, "message": "Pulizia completata"})


    @app.route("/admin/template-preview-file/<template_id>", methods=["GET"])
    def admin_template_preview_file(template_id):
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        tpl = template_service.get_template_by_id(template_id)
        if not tpl:
            return jsonify({"success": False, "message": "Template non trovato"}), 404

        template_file = tpl.get("template_file")
        if not template_file:
            return jsonify({"success": False, "message": "Template file mancante"}), 404

        path = os.path.join(paths.ASSETS_FOLDER, template_file)
        if not os.path.exists(path):
            return jsonify({"success": False, "message": "File template non trovato"}), 404

        return send_file(path)  


    @app.route("/admin/template-render-preview", methods=["POST"])
    def admin_template_render_preview():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        if "photo" not in request.files:
            return jsonify({"success": False, "message": "Nessuna foto"}), 400

        file = request.files["photo"]
        template_id = request.form.get("template_id", "").strip()

        if not template_id:
            return jsonify({"success": False, "message": "Template ID mancante"}), 400

        tpl = template_service.get_template_by_id(template_id)
        if not tpl:
            return jsonify({"success": False, "message": "Template non trovato"}), 404

        try:
            img = Image.open(file.stream)
            img = ImageOps.exif_transpose(img).convert("RGB")
        except Exception:
            return jsonify({"success": False, "message": "Immagine non valida"}), 400

        config = config_service.load_config()

        try:
            # copia locale del template per override temporaneo
            tpl_runtime = dict(tpl)

            photo_fit = request.form.get("photo_fit", "").strip()
            if photo_fit in {"cover", "contain"}:
                tpl_runtime["photo_fit"] = photo_fit

            if tpl_runtime.get("mode") == "image_template_multi" or tpl_runtime.get("print_format") == "strip":
                tpl_runtime["photo_boxes"] = [
                    [
                        int(request.form.get("box1_x", "0")),
                        int(request.form.get("box1_y", "0")),
                        int(request.form.get("box1_w", "0")),
                        int(request.form.get("box1_h", "0")),
                    ],
                    [
                        int(request.form.get("box2_x", "0")),
                        int(request.form.get("box2_y", "0")),
                        int(request.form.get("box2_w", "0")),
                        int(request.form.get("box2_h", "0")),
                    ],
                    [
                        int(request.form.get("box3_x", "0")),
                        int(request.form.get("box3_y", "0")),
                        int(request.form.get("box3_w", "0")),
                        int(request.form.get("box3_h", "0")),
                    ],
                ]
            else:
                tpl_runtime["photo_box"] = [
                    int(request.form.get("photo_x", "0")),
                    int(request.form.get("photo_y", "0")),
                    int(request.form.get("photo_w", "0")),
                    int(request.form.get("photo_h", "0")),
                ]

            mode = tpl_runtime.get("mode")

            if mode == "image_template":
                final = image_service.render_image_template(img, tpl_runtime, config)
            elif mode == "image_template_multi":
                final = image_service.render_image_template_multi(img, tpl_runtime, config)
            elif mode == "generated":
                final = image_service.render_generated_10x15(img, config, tpl_runtime)
            elif mode == "auto_orientation":
                final = image_service.render_auto_orientation_template(img, tpl_runtime, config)
            else:
                final = image_service.prepare_10x15(img)

            preview = final.copy()
            preview.thumbnail((450, 750))

            buffer = BytesIO()
            preview.save(buffer, format="JPEG", quality=88)
            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

            return jsonify({
                "success": True,
                "preview": f"data:image/jpeg;base64,{encoded}"
            })

        except Exception as e:
            return jsonify({"success": False, "message": f"Errore rendering: {str(e)}"}), 500


    @app.route("/admin/device-limits", methods=["GET"])
    def admin_device_limits():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        return jsonify({
            "success": True,
            "max_prints_per_mac": device_limit_service.get_global_limit(),
            "devices": device_limit_service.list_devices()
        })


    @app.route("/admin/device-limits/config", methods=["POST"])
    def admin_device_limits_config():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        try:
            limit = int(request.form.get("max_prints_per_mac", "3"))
            if limit < 1 or limit > 500:
                return jsonify({"success": False, "message": "Limite non valido"}), 400

            device_limit_service.set_global_limit(limit)
            return jsonify({"success": True, "message": "Limite per MAC aggiornato"})
        except Exception:
            return jsonify({"success": False, "message": "Valore non valido"}), 400


    @app.route("/admin/device-limits/reset", methods=["POST"])
    def admin_device_limits_reset():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        mac = request.form.get("mac", "").strip()
        ok = device_limit_service.reset_device(mac)

        if not ok:
            return jsonify({"success": False, "message": "MAC non valido"}), 400

        return jsonify({"success": True, "message": "Contatore dispositivo azzerato"})

    
    @app.route("/admin/print-quotas", methods=["GET"])
    def admin_print_quotas():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        return jsonify({
            "success": True,
            "event_code": print_quota_service.get_event_code(),
            "default_limit_per_identity": print_quota_service.get_default_limit(),
            "records": print_quota_service.list_records()
        })

    
    @app.route("/admin/print-quotas/config", methods=["POST"])
    def admin_print_quotas_config():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        try:
            event_code = request.form.get("event_code", "").strip()
            limit = int(request.form.get("default_limit_per_identity", "3"))

            if limit < 1 or limit > 500:
                return jsonify({"success": False, "message": "Limite non valido"}), 400

            print_quota_service.set_event_code(event_code or "EVENTO2026")
            print_quota_service.set_default_limit(limit)

            return jsonify({"success": True, "message": "Configurazione quote aggiornata"})
        except Exception:
            return jsonify({"success": False, "message": "Valori non validi"}), 400

    
    @app.route("/admin/print-quotas/reset", methods=["POST"])
    def admin_print_quotas_reset():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        identity_key = request.form.get("identity_key", "").strip()
        if not identity_key:
            return jsonify({"success": False, "message": "Identity key mancante"}), 400

        print_quota_service.reset_identity(identity_key)
        return jsonify({"success": True, "message": "Quota dispositivo azzerata"})
    
    def get_best_local_ip():
        try:
            import subprocess
            output = subprocess.check_output(
                "ip -4 addr show wlan0 | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){3}'",
                shell=True
            ).decode().strip()

            if output:
                return output
        except Exception:
            pass

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @app.route("/admin/event-qr-info", methods=["GET"])
    def admin_event_qr_info():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        event_code = print_quota_service.get_event_code()
        ip = get_best_local_ip()
        url = f"http://{ip}:5000/?event={event_code}"

        return jsonify({
            "success": True,
            "event_code": event_code,
            "ip": ip,
            "url": url
        })

    @app.route("/admin/event-qr-image", methods=["GET"])
    def admin_event_qr_image():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        event_code = print_quota_service.get_event_code()
        ip = get_best_local_ip()
        url = f"http://{ip}:5000/?event={event_code}"

        try:
            img = qrcode.make(url)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            return send_file(buffer, mimetype="image/png")
        except Exception as e:
            return jsonify({"success": False, "message": f"Errore generazione QR: {str(e)}"}), 500

    @app.route("/admin/event-qr-download", methods=["GET"])
    def admin_event_qr_download():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        event_code = print_quota_service.get_event_code()
        ip = get_best_local_ip()
        url = f"http://{ip}:5000/?event={event_code}"

        try:
            img = qrcode.make(url)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            filename = f"event_qr_{event_code}.png"
            return send_file(buffer, mimetype="image/png", as_attachment=True, download_name=filename)
        except Exception as e:
            return jsonify({"success": False, "message": f"Errore generazione QR: {str(e)}"}), 500


    def build_wifi_qr_string(ssid, password, security="WPA"):
        return f"WIFI:T:{security};S:{ssid};P:{password};;"

    @app.route("/admin/wifi-config", methods=["POST"])
    def admin_wifi_config():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        wifi_ssid = request.form.get("wifi_ssid", "").strip()
        wifi_password = request.form.get("wifi_password", "").strip()
        wifi_security = request.form.get("wifi_security", "WPA").strip() or "WPA"

        if not wifi_ssid:
            return jsonify({"success": False, "message": "SSID Wi-Fi obbligatorio"}), 400

        if wifi_security not in {"WPA", "WEP", "nopass"}:
            return jsonify({"success": False, "message": "Sicurezza Wi-Fi non valida"}), 400

        if wifi_security != "nopass" and not wifi_password:
            return jsonify({"success": False, "message": "Password Wi-Fi obbligatoria"}), 400

        config_service.save_config({
            "wifi_ssid": wifi_ssid,
            "wifi_password": wifi_password,
            "wifi_security": wifi_security,
        })

        return jsonify({"success": True, "message": "Configurazione Wi-Fi aggiornata"})    
   
   
    @app.route("/admin/qr-wifi-info", methods=["GET"])
    def admin_qr_wifi_info():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        config = config_service.load_config()
        return jsonify({
            "success": True,
            "wifi_ssid": config.get("wifi_ssid", ""),
            "wifi_password": config.get("wifi_password", ""),
            "wifi_security": config.get("wifi_security", "WPA")
        })

    @app.route("/admin/qr-wifi-image", methods=["GET"])
    def admin_qr_wifi_image():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        config = config_service.load_config()
        ssid = config.get("wifi_ssid", "")
        password = config.get("wifi_password", "")
        security = config.get("wifi_security", "WPA")

        if not ssid:
            return jsonify({"success": False, "message": "SSID Wi-Fi mancante"}), 400

        wifi_data = build_wifi_qr_string(ssid, password, security)

        try:
            img = qrcode.make(wifi_data)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            return send_file(buffer, mimetype="image/png")
        except Exception as e:
            return jsonify({"success": False, "message": f"Errore QR Wi-Fi: {str(e)}"}), 500


    @app.route("/admin/qr-wifi-download", methods=["GET"])
    def admin_qr_wifi_download():
        if not admin_required():
            return jsonify({"success": False, "message": "Non autorizzato"}), 403

        config = config_service.load_config()
        ssid = config.get("wifi_ssid", "")
        password = config.get("wifi_password", "")
        security = config.get("wifi_security", "WPA")

        if not ssid:
            return jsonify({"success": False, "message": "SSID Wi-Fi mancante"}), 400

        wifi_data = build_wifi_qr_string(ssid, password, security)

        try:
            img = qrcode.make(wifi_data)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            filename = f"wifi_qr_{ssid}.png"
            return send_file(buffer, mimetype="image/png", as_attachment=True, download_name=filename)
        except Exception as e:
            return jsonify({"success": False, "message": f"Errore QR Wi-Fi: {str(e)}"}), 500     