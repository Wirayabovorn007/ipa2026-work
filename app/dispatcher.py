"""Part 4: dispatch a validated request to the correct backend."""

from app.backends import ansible, common, netconf, netmiko_textfsm, restconf

_BACKENDS = {
    "restconf": restconf,
    "netconf": netconf,
    "ansible": ansible,
    "netmiko-textfsm": netmiko_textfsm,
}

# (method, action) -> (backend function name, argument kind)
# "name"    : backend(router, interface_name)
# "desired" : backend(router, desired_interface_dict)
# This is exactly the 9-entry capability matrix from the backend spec.
_OPERATIONS = {
    ("restconf", "status"): ("get_interface_state", "name"),
    ("restconf", "plan"): ("plan_interface", "desired"),
    ("restconf", "apply"): ("apply_interface", "desired"),
    ("netconf", "status"): ("get_interface_state", "name"),
    ("netconf", "plan"): ("plan_interface", "desired"),
    ("netconf", "apply"): ("apply_interface", "desired"),
    ("ansible", "apply"): ("apply_interface", "desired"),
    ("netmiko-textfsm", "status"): ("get_interface_state", "name"),
    ("netmiko-textfsm", "delete"): ("delete_interface", "name"),
}


def dispatch_request(data):
    """Run an already validated request and return the backend response."""
    try:
        method = data["method"]
        action = data["action"]
        router = data["router"]
        interface = data["desired"]["interface"]
    except (KeyError, TypeError):
        return common.error("backend_failed")

    op = _OPERATIONS.get((method, action))
    if op is None:
        return {"status": "error", "result": "invalid_action"}

    func_name, arg_kind = op
    # Look the function up at call time so it can be patched in tests.
    func = getattr(_BACKENDS[method], func_name)
    if arg_kind == "name":
        return func(router, interface["name"])
    return func(router, interface)