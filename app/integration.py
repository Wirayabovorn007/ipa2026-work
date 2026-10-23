"""Part 4: glue between Webex input (Part 1) and the backends (Parts 2-3)."""

import yaml

from app.backends import common
from app.core import validate_request
from app.dispatcher import dispatch_request

from app.request_handler import validate_webex_envelope


def _load_yaml(path):
    """Read the attachment once. Returns (data, error_response)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f), None
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError, RecursionError):
        return None, {"status": "error", "result": "invalid_yaml"}


def process_request(mentioned_people, attachment_path, bot_person_id):
    # 1. Mention / attachment envelope.
    error = validate_webex_envelope(
        mentioned_people, attachment_path, bot_person_id
    )
    if error is not None:
        return error

    # 2. Load the YAML once, then validate the parsed request.
    data, error = _load_yaml(attachment_path)
    if error is not None:
        return error
    verdict = validate_request(data)
    if verdict.get("status") != "ok":
        return verdict

    # 3. Only accepted requests reach a backend; its response is returned
    #    unchanged.
    try:
        return dispatch_request(data)
    except Exception as exc:
        return common.error(common.classify_exception(exc))