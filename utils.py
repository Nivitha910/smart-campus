from functools import wraps
from bson import ObjectId
from bson.errors import InvalidId
from flask import abort, session


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            abort(401)
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                abort(401)
            if session.get("role") != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def valid_object_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None
