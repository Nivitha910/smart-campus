# Smart Campus Management System

A responsive Flask and MongoDB application for campus complaints and attendance corrections.

## Features

- Secure student registration and login
- Student dashboard with real MongoDB statistics
- Complaint submission, search, filters, attachments, and history
- Attendance correction submissions and evidence uploads
- Admin complaint processing and remarks
- Admin attendance approve/reject workflow with audit logs
- Student management and complaint/attendance profiles
- In-app notifications
- Chart.js analytics and CSV export
- Role-based access, CSRF protection, password hashing, upload validation, and pagination

## Requirements

- Python 3.10+
- MongoDB Community Server or MongoDB Atlas

## Setup

1. Copy the environment template:

```powershell
Copy-Item .env.example .env
```

2. Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

3. Configure `.env`:

For local MongoDB:

```text
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=smart_campus
SECRET_KEY=replace_with_a_long_random_secret
UPLOAD_FOLDER=static/uploads
SEED_DEMO_DATA=true
```

For MongoDB Atlas, set `MONGO_URI` to the Atlas connection string with your database user credentials. `MONGO_DB_NAME` selects the database for either connection mode. Keep credentials only in `.env`.

Set `SESSION_COOKIE_SECURE=true` when serving the application over HTTPS.

4. Start MongoDB, initialize the environment, and run:

```powershell
py app.py
```

Open `http://127.0.0.1:5000`.

Indexes and optional demo accounts are initialized on startup when MongoDB is available. If MongoDB cannot be reached, the app logs the connection problem; `/health` reports `503` until the database is available. Database-backed pages show a service-unavailable message rather than pretending database operations succeeded.

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Administrator | admin@campus.com | Admin@123 |
| Student | student@campus.com | Student@123 |

Demo seeding is controlled by `SEED_DEMO_DATA=true`. Existing accounts are never overwritten.

## Tests

```powershell
py -m pytest -q
```
