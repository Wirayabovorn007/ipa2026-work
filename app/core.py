import yaml

ALLOWED_ROUTERS = {
    "10.0.29.101",
    "10.0.29.102",
    "10.0.29.103",
    "10.0.29.104",
    "10.0.29.105",
}

METHOD_ACTIONS = {
    "restconf": {"status", "plan", "apply"},
    "netconf": {"status", "plan", "apply"},
    "ansible": {"apply"},
    "netmiko-textfsm": {"status", "delete"},
}

ADMIN_STATES = {"up", "down"}
FULL_STATE_ACTIONS = {"plan", "apply"}


def _error(code):
    return {"status": "error", "result": code}


def _is_blank(value):
    """True for a missing/null value or an empty/whitespace-only string."""
    return value is None or (isinstance(value, str) and not value.strip())


def validate_request(data):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    if not isinstance(data, dict):
        return _error("invalid_yaml")

    # 1. version: must be the integer 1 (not "1", 1.0 or True)
    version = data.get("version")
    if type(version) is not int or version != 1:
        return _error("invalid_version")

    # 2. router
    router = data.get("router")
    if _is_blank(router):
        return _error("missing_router")
    if not isinstance(router, str) or router not in ALLOWED_ROUTERS:
        return _error("invalid_router")

    # 3. method
    method = data.get("method")
    if _is_blank(method):
        return _error("missing_method")
    if not isinstance(method, str) or method not in METHOD_ACTIONS:
        return _error("invalid_method")

    # 4. action (checked against the selected method)
    action = data.get("action")
    if _is_blank(action):
        return _error("missing_action")
    if not isinstance(action, str) or action not in METHOD_ACTIONS[method]:
        return _error("invalid_action")

    # 5. desired / interface / name
    desired = data.get("desired")
    if not isinstance(desired, dict):
        return _error("missing_desired")
    interface = desired.get("interface")
    if not isinstance(interface, dict):
        return _error("missing_interface")
    name = interface.get("name")
    if _is_blank(name):
        return _error("missing_interface_name")

    # 6. complete desired state: plan and apply only
    if action in FULL_STATE_ACTIONS:
        if _is_blank(interface.get("ipv4")):
            return _error("missing_ipv4")
        if _is_blank(interface.get("description")):
            return _error("missing_description")
        admin_state = interface.get("admin_state")
        if admin_state is None:
            return _error("missing_admin_state")
        if not isinstance(admin_state, str) or admin_state not in ADMIN_STATES:
            return _error("invalid_admin_state")

    return {"status": "ok", "result": "accepted"}


def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError, RecursionError):
        return _error("invalid_yaml")
    return validate_request(data)