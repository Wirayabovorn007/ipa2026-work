from app.planner import build_plan


def plan_interface(
    router,
    desired_interface,
    get_interface_state,
):
    """Build a Part 2 plan from backend status."""
    state = get_interface_state(router, desired_interface["name"])
    if state.get("status") != "ok":
        return state  # backend error returned unchanged

    result = state.get("result")
    if result == "found":
        current = state.get("interface")
    elif result == "not_found":
        current = None
    else:
        return {"status": "error", "result": "backend_failed"}
    return build_plan(desired_interface, current)