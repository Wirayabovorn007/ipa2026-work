from urllib.parse import quote

from app.backends import common
from app.backends.planning import plan_interface as _plan

_HEADERS = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json",
}


def _status_url(router, name):
    return "https://%s/restconf/data/ietf-interfaces:interfaces/interface=%s" % (
        router,
        quote(str(name), safe=""),
    )


def _native_url(router, number):
    return "https://%s/restconf/data/Cisco-IOS-XE-native:native/interface/Loopback=%s" % (
        router,
        number,
    )


def _default_http_get(url):
    import requests

    requests.packages.urllib3.disable_warnings()
    return requests.get(
        url, auth=common.credentials(), headers=_HEADERS, verify=False, timeout=15
    )


def _default_http_put(url, json=None):
    import requests

    requests.packages.urllib3.disable_warnings()
    return requests.put(
        url,
        json=json,
        auth=common.credentials(),
        headers=_HEADERS,
        verify=False,
        timeout=30,
    )


def _normalize(body, requested_name):
    if not isinstance(body, dict):
        raise ValueError("malformed RESTCONF body")
    node = body.get("ietf-interfaces:interface", body.get("interface"))
    if isinstance(node, list):
        node = node[0] if node else None
    if not isinstance(node, dict):
        raise ValueError("missing interface node")

    ipv4 = None
    ip_node = node.get("ietf-ip:ipv4", node.get("ipv4")) or {}
    addresses = ip_node.get("address") or []
    if isinstance(addresses, dict):
        addresses = [addresses]
    if addresses:
        first = addresses[0]
        mask = first.get("netmask", first.get("prefix-length"))
        ipv4 = common.to_cidr(first["ip"], mask)

    enabled = node.get("enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() == "true"

    return {
        "name": node.get("name", requested_name),
        "ipv4": ipv4,
        "description": node.get("description"),
        "admin_state": "up" if enabled else "down",
    }


def get_interface_state(
    router,
    interface_name,
    http_get=None,
):
    """Return normalized interface status using RESTCONF."""
    get = http_get or _default_http_get
    try:
        resp = get(_status_url(router, interface_name))
        code = resp.status_code
        if code == 404:
            return common.not_found()
        if code in (401, 403):
            return common.error("authentication_failed")
        if code != 200:
            return common.error("backend_failed")
        return {
            "status": "ok",
            "result": "found",
            "interface": _normalize(resp.json(), interface_name),
        }
    except Exception as exc:
        return common.error(common.classify_exception(exc))


def plan_interface(
    router,
    desired_interface,
    http_get=None,
):
    """Return create/update/no_change plan using RESTCONF status."""
    return _plan(
        router,
        desired_interface,
        lambda r, n: get_interface_state(r, n, http_get=http_get),
    )


def apply_interface(
    router,
    desired_interface,
    http_put=None,
):
    """Apply complete desired interface state using RESTCONF."""
    put = http_put or _default_http_put
    try:
        number = common.loopback_number(desired_interface["name"])
        address, mask = common.split_cidr(desired_interface["ipv4"])
        loopback = {
            "name": int(number),
            "description": desired_interface["description"],
            "ip": {"address": {"primary": {"address": address, "mask": mask}}},
        }
        if desired_interface["admin_state"] == "down":
            loopback["shutdown"] = [None]
        payload = {"Cisco-IOS-XE-native:Loopback": loopback}

        resp = put(_native_url(router, number), json=payload)
        code = resp.status_code
        if code in (200, 201, 204):
            return {"status": "ok", "result": "applied"}
        if code in (401, 403):
            return common.error("authentication_failed")
        return common.error("backend_failed")
    except Exception as exc:
        return common.error(common.classify_exception(exc))