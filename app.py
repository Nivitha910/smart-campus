import os
import re
import csv
import io
from datetime import datetime, timezone
from bson import ObjectId
from flask import Flask, Response, abort, jsonify, render_template, redirect, url_for, request, session, flash, send_from_directory
from flask_wtf.csrf import CSRFProtect
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from database import mongo
from utils import login_required, role_required, valid_object_id


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    CSRFProtect(app)
    mongo.init_app(app)
    db = mongo.cx[app.config["MONGO_DB_NAME"]]

    def init_database():
        db.users.create_index("email", unique=True)
        db.users.create_index("roll_number", unique=True, sparse=True)
        db.complaints.create_index("complaint_id", unique=True)
        db.complaints.create_index([("student_id", 1), ("status", 1), ("created_at", -1)])
        db.attendance_requests.create_index("request_id", unique=True)
        db.attendance_requests.create_index([("student_id", 1), ("status", 1), ("created_at", -1)])
        db.notifications.create_index([("recipient_id", 1), ("is_read", 1), ("created_at", -1)])

        if app.config["SEED_DEMO_DATA"]:
            if db.users.count_documents({"email": "admin@campus.com"}) == 0:
                db.users.insert_one({
                    "name": "Campus Administrator", "email": "admin@campus.com",
                    "password_hash": generate_password_hash("Admin@123"),
                    "role": "admin", "department": "Administration", "year": "",
                    "roll_number": "", "created_at": datetime.now(timezone.utc), "is_active": True
                })
            if db.users.count_documents({"email": "student@campus.com"}) == 0:
                db.users.insert_one({
                    "name": "Demo Student", "email": "student@campus.com",
                    "password_hash": generate_password_hash("Student@123"),
                    "role": "student", "department": "Computer Science", "year": "3",
                    "roll_number": "CS2023001", "created_at": datetime.now(timezone.utc), "is_active": True
                })

    def notify(recipient_id, title, message, notification_type="info", related_id=None):
        db.notifications.insert_one({
            "recipient_id": recipient_id, "title": title, "message": message,
            "notification_type": notification_type, "related_id": related_id,
            "is_read": False, "created_at": datetime.now(timezone.utc)
        })

    def save_upload(file):
        if not file or not file.filename:
            return ""
        allowed = {"png", "jpg", "jpeg", "pdf", "doc", "docx"}
        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext not in allowed:
            return None
        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{secure_filename(file.filename)}"
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        return filename

    def new_id(prefix):
        now = datetime.now(timezone.utc)
        return f"{prefix}-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S%f')[-6:]}"

    def current_user():
        uid = valid_object_id(session.get("user_id"))
        return db.users.find_one({"_id": uid}) if uid else None

    def page(query, collection, sort, page_num, per_page=10):
        total = collection.count_documents(query)
        items = list(collection.find(query).sort(sort).skip((page_num - 1) * per_page).limit(per_page))
        pages = max(1, (total + per_page - 1) // per_page)
        return items, pages, total

    @app.route("/")
    def index():
        if "user_id" not in session:
            return redirect(url_for("login"))
        return redirect(url_for("admin_dashboard" if session["role"] == "admin" else "student_dashboard"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = db.users.find_one({"email": email})
            if not user or not check_password_hash(user["password_hash"], password) or not user.get("is_active", True):
                flash("Invalid email or password.", "danger")
                return render_template("login.html")
            session.clear()
            session.permanent = True
            session["user_id"] = str(user["_id"])
            session["role"] = user["role"]
            session["name"] = user["name"]
            flash("Welcome back!", "success")
            return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "student_dashboard"))
        return render_template("login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            data = {key: request.form.get(key, "").strip() for key in
                    ["name", "email", "roll_number", "department", "year", "password", "confirm_password"]}
            email = data["email"].lower()
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                flash("Enter a valid email address.", "danger")
            elif data["password"] != data["confirm_password"]:
                flash("Passwords do not match.", "danger")
            elif len(data["password"]) < 8:
                flash("Password must be at least 8 characters.", "danger")
            elif not all(data[key] for key in ("name", "roll_number", "department", "year")):
                flash("Complete all required fields.", "danger")
            elif db.users.find_one({"$or": [{"email": email}, {"roll_number": data["roll_number"].upper()}]}):
                flash("Email or roll number is already registered.", "danger")
            else:
                user = db.users.insert_one({
                    "name": data["name"], "email": email, "roll_number": data["roll_number"].upper(),
                    "department": data["department"], "year": data["year"],
                    "password_hash": generate_password_hash(data["password"]),
                    "role": "student", "created_at": datetime.now(timezone.utc), "is_active": True
                })
                session.clear()
                session.permanent = True
                session["user_id"] = str(user.inserted_id)
                session["role"] = "student"
                session["name"] = data["name"]
                flash("Registration successful.", "success")
                return redirect(url_for("student_dashboard"))
        return render_template("register.html")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/student/dashboard")
    @role_required("student")
    def student_dashboard():
        uid = ObjectId(session["user_id"])
        complaint_status = list(db.complaints.aggregate([
            {"$match": {"student_id": uid}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]))
        attendance_status = list(db.attendance_requests.aggregate([
            {"$match": {"student_id": uid}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]))
        def counts(items):
            return {item["_id"]: item["count"] for item in items}
        cs, ats = counts(complaint_status), counts(attendance_status)
        complaints = list(db.complaints.find({"student_id": uid}).sort("created_at", -1).limit(5))
        attendance = list(db.attendance_requests.find({"student_id": uid}).sort("created_at", -1).limit(5))
        notifications = list(db.notifications.find({"recipient_id": uid}).sort("created_at", -1).limit(5))
        return render_template("student_dashboard.html", cs=cs, ats=ats,
                               complaints=complaints, attendance=attendance, notifications=notifications)

    @app.route("/student/complaints", methods=["GET", "POST"])
    @role_required("student")
    def student_complaints():
        uid = ObjectId(session["user_id"])
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            category = request.form.get("category", "")
            priority = request.form.get("priority", "Medium")
            categories = {"Classroom", "Projector", "Wi-Fi", "Drinking Water", "Laboratory Equipment",
                          "Washroom", "Hostel", "Electrical Issues", "Cleanliness", "Other"}
            priorities = {"Low", "Medium", "High", "Urgent"}
            if not title or not description or category not in categories or priority not in priorities:
                flash("Provide a title, description, valid category, and valid priority.", "danger")
            else:
                attachment = save_upload(request.files.get("attachment"))
                if attachment is None:
                    flash("Unsupported attachment type.", "danger")
                    return redirect(url_for("student_complaints"))
                user = current_user()
                complaint_id = new_id("CMP")
                result = db.complaints.insert_one({
                    "complaint_id": complaint_id, "student_id": uid,
                    "student_name": user["name"], "roll_number": user.get("roll_number", ""),
                    "department": user.get("department", ""), "category": category,
                    "title": title, "description": description, "priority": priority,
                    "attachment": attachment, "status": "Pending", "assigned_department": "",
                    "admin_remarks": "", "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc), "resolved_at": None
                })
                notify(uid, "Complaint submitted", f"Complaint {complaint_id} was submitted.", "complaint", result.inserted_id)
                admins = db.users.find({"role": "admin"})
                for admin in admins:
                    notify(admin["_id"], "New complaint received", f"{user['name']} submitted {complaint_id}.", "complaint", result.inserted_id)
                flash("Complaint submitted successfully.", "success")
                return redirect(url_for("student_complaints"))

        query = {"student_id": uid}
        if request.args.get("status"):
            query["status"] = request.args["status"]
        if request.args.get("category"):
            query["category"] = request.args["category"]
        search = request.args.get("search", "").strip()
        if search:
            query["complaint_id"] = search
        page_num = max(1, int(request.args.get("page", 1)))
        items, pages, total = page(query, db.complaints, "created_at", page_num)
        return render_template("complaints.html", complaints=items, pages=pages, page=page_num, total=total)

    @app.route("/student/attendance", methods=["GET", "POST"])
    @role_required("student")
    def student_attendance():
        uid = ObjectId(session["user_id"])
        if request.method == "POST":
            subject = request.form.get("subject", "").strip()
            attendance_date = request.form.get("attendance_date", "")
            reason = request.form.get("reason", "").strip()
            if not subject or not attendance_date or not reason:
                flash("Subject, date, and reason are required.", "danger")
            else:
                attachment = save_upload(request.files.get("attachment"))
                if attachment is None:
                    flash("Unsupported evidence type.", "danger")
                    return redirect(url_for("student_attendance"))
                user = current_user()
                request_id = new_id("ATT")
                result = db.attendance_requests.insert_one({
                    "request_id": request_id, "student_id": uid, "student_name": user["name"],
                    "roll_number": user.get("roll_number", ""), "department": user.get("department", ""),
                    "year": user.get("year", ""), "subject": subject, "attendance_date": attendance_date,
                    "reason": reason, "attachment": attachment, "status": "Pending",
                    "admin_remarks": "", "processed_by": None, "processed_at": None,
                    "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)
                })
                notify(uid, "Attendance request submitted", f"Request {request_id} was submitted.", "attendance", result.inserted_id)
                for admin in db.users.find({"role": "admin"}):
                    notify(admin["_id"], "New attendance request", f"{user['name']} submitted {request_id}.", "attendance", result.inserted_id)
                flash("Attendance correction request submitted.", "success")
                return redirect(url_for("student_attendance"))
        query = {"student_id": uid}
        if request.args.get("status"):
            query["status"] = request.args["status"]
        search = request.args.get("search", "").strip()
        if search:
            query["request_id"] = search
        page_num = max(1, int(request.args.get("page", 1)))
        items, pages, total = page(query, db.attendance_requests, "created_at", page_num)
        return render_template("attendance.html", requests=items, pages=pages, page=page_num, total=total)

    @app.route("/student/profile", methods=["GET", "POST"])
    @role_required("student")
    def student_profile():
        uid = ObjectId(session["user_id"])
        if request.method == "POST":
            db.users.update_one({"_id": uid}, {"$set": {
                "name": request.form.get("name", "").strip(),
                "department": request.form.get("department", "").strip(),
                "year": request.form.get("year", "").strip()
            }})
            flash("Profile updated.", "success")
            session["name"] = request.form.get("name", "").strip()
        return render_template("profile.html", user=current_user())

    @app.route("/admin/dashboard")
    @role_required("admin")
    def admin_dashboard():
        complaint_status = list(db.complaints.aggregate([
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]))
        attendance_status = list(db.attendance_requests.aggregate([
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]))
        category_stats = list(db.complaints.aggregate([
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]))
        department_stats = list(db.users.aggregate([
            {"$match": {"role": "student"}},
            {"$group": {"_id": "$department", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]))
        cs = {item["_id"]: item["count"] for item in complaint_status}
        ats = {item["_id"]: item["count"] for item in attendance_status}
        stats = {
            "students": db.users.count_documents({"role": "student"}),
            "complaints": db.complaints.count_documents({}),
            "attendance": db.attendance_requests.count_documents({})
        }
        recent_complaints = list(db.complaints.find().sort("created_at", -1).limit(5))
        recent_attendance = list(db.attendance_requests.find().sort("created_at", -1).limit(5))
        return render_template("admin_dashboard.html", stats=stats, cs=cs, ats=ats,
                               category_stats=category_stats, department_stats=department_stats,
                               recent_complaints=recent_complaints, recent_attendance=recent_attendance)

    @app.route("/admin/complaints", methods=["GET", "POST"])
    @role_required("admin")
    def admin_complaints():
        if request.method == "POST":
            complaint_id = request.form.get("_id", "")
            oid = valid_object_id(complaint_id)
            if not oid:
                flash("Invalid complaint.", "danger")
                return redirect(url_for("admin_complaints"))
            complaint = db.complaints.find_one({"_id": oid})
            if complaint:
                old_status = complaint["status"]
                new_status = request.form.get("status", old_status)
                remarks = request.form.get("remarks", "").strip()
                assigned = request.form.get("assigned_department", "").strip()
                if new_status not in {"Pending", "In Progress", "Resolved", "Rejected"}:
                    flash("Invalid complaint status.", "danger")
                    return redirect(url_for("admin_complaints"))
                update = {
                    "status": new_status,
                    "admin_remarks": remarks,
                    "assigned_department": assigned,
                    "updated_at": datetime.now(timezone.utc)
                }
                if new_status == "Resolved":
                    update["resolved_at"] = datetime.now(timezone.utc)
                db.complaints.update_one({"_id": oid}, {"$set": update})
                db.complaint_updates.insert_one({
                    "complaint_id": oid, "updated_by": ObjectId(session["user_id"]),
                    "old_status": old_status, "new_status": new_status, "remarks": remarks,
                    "created_at": datetime.now(timezone.utc)
                })
                notify(complaint["student_id"], "Complaint status updated",
                       f"{complaint['complaint_id']} is now {new_status}. Remarks: {remarks or 'None'}",
                       "complaint", oid)
                flash("Complaint updated.", "success")
            return redirect(url_for("admin_complaints"))

        query = {}
        for field in ("status", "category", "priority"):
            if request.args.get(field):
                query[field] = request.args[field]
        search = request.args.get("search", "").strip()
        if search:
            query["$or"] = [
                {"complaint_id": search},
                {"student_name": {"$regex": re.escape(search), "$options": "i"}},
                {"roll_number": {"$regex": re.escape(search), "$options": "i"}}
            ]
        page_num = max(1, int(request.args.get("page", 1)))
        items, pages, total = page(query, db.complaints, "created_at", page_num)
        return render_template("admin_complaints.html", complaints=items, pages=pages, page=page_num, total=total)

    @app.route("/admin/attendance", methods=["GET", "POST"])
    @role_required("admin")
    def admin_attendance():
        if request.method == "POST":
            oid = valid_object_id(request.form.get("_id", ""))
            action = request.form.get("action")
            if not oid or action not in ("approve", "reject"):
                flash("Invalid attendance request or action.", "danger")
                return redirect(url_for("admin_attendance"))
            new_status = "Approved" if action == "approve" else "Rejected"
            remarks = request.form.get("remarks", "").strip()
            admin_id = ObjectId(session["user_id"])
            decided_at = datetime.now(timezone.utc)
            attendance = db.attendance_requests.find_one_and_update(
                {"_id": oid, "status": "Pending"}, {"$set": {
                "status": new_status, "admin_remarks": remarks,
                "processed_by": admin_id, "processed_at": decided_at,
                "updated_at": decided_at
            }}, return_document=ReturnDocument.AFTER)
            if not attendance:
                if db.attendance_requests.find_one({"_id": oid}):
                    flash("This request has already been finalized.", "warning")
                else:
                    flash("Attendance request not found.", "danger")
                return redirect(url_for("admin_attendance"))
            db.attendance_audit_logs.insert_one({
                "request_id": oid, "student_id": attendance["student_id"], "admin_id": admin_id,
                "previous_status": "Pending", "new_status": new_status,
                "remarks": remarks, "action_timestamp": decided_at
            })
            notify(attendance["student_id"], f"Attendance request {new_status.lower()}",
                   f"{attendance['request_id']} was {new_status.lower()}. Remarks: {remarks or 'None'}",
                   "attendance", oid)
            flash(f"Attendance request {new_status.lower()}.", "success")
            return redirect(url_for("admin_attendance"))

        query = {}
        for field in ("department", "subject", "status"):
            if request.args.get(field):
                query[field] = request.args[field]
        if request.args.get("date"):
            query["attendance_date"] = request.args["date"]
        search = request.args.get("search", "").strip()
        if search:
            query["$or"] = [
                {"request_id": search},
                {"student_name": {"$regex": re.escape(search), "$options": "i"}},
                {"roll_number": {"$regex": re.escape(search), "$options": "i"}}
            ]
        page_num = max(1, int(request.args.get("page", 1)))
        items, pages, total = page(query, db.attendance_requests, "created_at", page_num)
        return render_template("admin_attendance.html", requests=items, pages=pages, page=page_num, total=total)

    @app.route("/admin/students")
    @role_required("admin")
    def admin_students():
        query = {"role": "student"}
        if request.args.get("department"):
            query["department"] = request.args["department"]
        if request.args.get("year"):
            query["year"] = request.args["year"]
        search = request.args.get("search", "").strip()
        if search:
            query["$or"] = [
                {"name": {"$regex": re.escape(search), "$options": "i"}},
                {"roll_number": {"$regex": re.escape(search), "$options": "i"}}
            ]
        page_num = max(1, int(request.args.get("page", 1)))
        items, pages, total = page(query, db.users, "created_at", page_num)
        departments = db.users.distinct("department", {"role": "student"})
        years = db.users.distinct("year", {"role": "student"})
        return render_template("students.html", students=items, departments=departments, years=years,
                               pages=pages, page=page_num, total=total)

    @app.route("/admin/students/<student_id>")
    @role_required("admin")
    def admin_student_detail(student_id):
        oid = valid_object_id(student_id)
        if not oid:
            abort(400)
        student = db.users.find_one({"_id": oid, "role": "student"})
        if not student:
            abort(404)
        complaints = list(db.complaints.find({"student_id": oid}).sort("created_at", -1))
        attendance = list(db.attendance_requests.find({"student_id": oid}).sort("created_at", -1))
        return render_template("profile.html", user=student, student_view=True,
                               complaints=complaints, attendance=attendance)

    @app.route("/notifications")
    @login_required
    def notifications():
        uid = ObjectId(session["user_id"])
        items = list(db.notifications.find({"recipient_id": uid}).sort("created_at", -1).limit(100))
        unread = db.notifications.count_documents({"recipient_id": uid, "is_read": False})
        return render_template("notifications.html", notifications=items, unread=unread)

    @app.route("/notifications/read", methods=["POST"])
    @login_required
    def read_notifications():
        uid = ObjectId(session["user_id"])
        notification_id = request.form.get("_id")
        if notification_id:
            oid = valid_object_id(notification_id)
            if oid:
                db.notifications.update_one({"_id": oid, "recipient_id": uid}, {"$set": {"is_read": True}})
        else:
            db.notifications.update_many({"recipient_id": uid, "is_read": False}, {"$set": {"is_read": True}})
        return redirect(url_for("notifications"))

    @app.route("/uploads/<path:filename>")
    @login_required
    def uploaded_file(filename):
        safe = secure_filename(filename)
        if not safe:
            abort(404)
        query = {"attachment": safe}
        if session.get("role") != "admin":
            query["student_id"] = ObjectId(session["user_id"])
        if not db.complaints.find_one(query) and not db.attendance_requests.find_one(query):
            abort(404)
        return send_from_directory(app.config["UPLOAD_FOLDER"], safe, as_attachment=True)

    @app.route("/admin/export/complaints")
    @role_required("admin")
    def export_complaints():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Complaint ID", "Student", "Roll", "Department", "Category", "Priority", "Status", "Created"])
        for item in db.complaints.find().sort("created_at", -1):
            writer.writerow([item["complaint_id"], item["student_name"], item["roll_number"], item["department"],
                             item["category"], item["priority"], item["status"], item["created_at"]])
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment;filename=complaints.csv"})

    @app.errorhandler(401)
    def unauthorized(_error):
        return redirect(url_for("login"))

    @app.errorhandler(403)
    def forbidden(_error):
        flash("You are not authorized to access this page.", "danger")
        return redirect(url_for("index"))

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    @app.errorhandler(PyMongoError)
    def database_unavailable(error):
        app.logger.error("MongoDB operation failed: %s", error)
        return render_template("503.html"), 503

    @app.route("/health")
    def health():
        try:
            db.command("ping")
        except PyMongoError as error:
            app.logger.warning("MongoDB health check failed: %s", error)
            return jsonify({"status": "unavailable", "database": "mongodb"}), 503
        return jsonify({"status": "ok", "database": "mongodb"}), 200

    try:
        init_database()
    except PyMongoError as exc:
        app.logger.warning("MongoDB unavailable during startup: %s", exc)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
