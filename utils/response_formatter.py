from flask import jsonify


def success_response(payload=None, message=None, status=200):
    response = {
        "success": True,
    }

    if payload is not None:
        response.update(
            payload
            if isinstance(payload, dict)
            else {"data": payload}
        )

    if message:
        response["message"] = message

    return jsonify(response), status


def error_response(code, message, details=None, status=400):
    response = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }

    return jsonify(response), status