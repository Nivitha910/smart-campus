import re
import pytest
from flask import render_template

from app import app, create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app.test_client()


def test_login_page(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Welcome back" in response.data


def test_register_page(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b"Student registration" in response.data


def test_private_page_requires_login(client):
    response = client.get("/student/dashboard")
    assert response.status_code in (302, 401)


def test_admin_dashboard_renders_without_analytics_data():
    with app.test_request_context("/admin/dashboard"):
        html = render_template(
            "admin_dashboard.html",
            stats=None,
            cs=None,
            ats=None,
            category_stats=[],
            department_stats=[],
            recent_complaints=[],
            recent_attendance=[],
        )

    assert "Total Students</span><h3>0</h3>" in html
    assert "No complaint category data" in html
    assert "No department data" in html


def test_admin_dashboard_renders_department_and_category_analytics():
    with app.test_request_context("/admin/dashboard"):
        html = render_template(
            "admin_dashboard.html",
            stats={"students": 1, "attendance": 0},
            cs={},
            ats={},
            category_stats=[{"_id": "Wi-Fi", "count": 2}],
            department_stats=[{"_id": "Engineering", "count": 2}],
            recent_complaints=[],
            recent_attendance=[],
        )

    assert "Wi-Fi" in html
    assert "Engineering" in html
    assert "Students by department" in html
    assert re.search(r"width:\s*100(?:\.0)?%", html)
