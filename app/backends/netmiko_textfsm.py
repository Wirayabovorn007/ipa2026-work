import re

from app.backends import common

import logging
import re

from app.backends import common

logger = logging.getLogger(__name__)


def _canon(name):
    """Canonical comparison form; Lo123 == Loopback123."""
    s = str(name or "").strip()
    m = re.fullmatch(r"([A-Za-z-]+)\s*(\d[\d/.:]*)", s)
    if m:
        prefix, rest = m.group(1).lower(), m.group(2)
        if len(prefix) >= 2 and "loopback".startswith(prefix):
            return "loopback" + rest
        return prefix + rest
    return s.lower()


def _get(rec, *keys):
    lowered = {str(k).lower(): v for k, v in rec.items()}
    for k in keys:
        if k in lowered:
            return lowered[k]
    return None


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _records(data):
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise ValueError("unparsed CLI output")


def _normalize(interface_name, ip_info, descriptions):
    """Return a normalized interface dict, or None when it does not exist."""
    wanted = _canon(interface_name)
    rec = None
    for r in _records(ip_info):
        if _canon(_get(r, "intf", "interface", "name")) == wanted:
            rec = r
            break
    if rec is None:
        return None

    ipv4 = None
    ip = _first(_get(rec, "ipaddr", "ip_address", "ipv4"))
    if ip:
        mask = _first(_get(rec, "mask", "prefix_length", "prefixlen", "netmask"))
        if mask in (None, ""):
            raise ValueError("IP address without prefix length")
        ipv4 = common.to_cidr(ip, mask)

    link = str(_get(rec, "link_status", "status") or "").lower()
    admin_state = "down" if "administratively down" in link else "up"

    description = None
    for d in _records(descriptions):
        if _canon(_get(d, "port", "interface", "intf")) == wanted:
            description = _get(d, "description", "descrip", "desc")
            break
    if isinstance(description, str):
        description = description.strip() or None

    return {
        "name": interface_name,
        "ipv4": ipv4,
        "description": description,
        "admin_state": admin_state,
    }


def _connect(router):
    from netmiko import ConnectHandler

    user, password = common.credentials()
    return ConnectHandler(
        device_type="cisco_ios",
        host=router,
        username=user,
        password=password,
        timeout=20,
        conn_timeout=20,
    )

def _default_get(router, interface_name):
    cmd = "show ip interface %s" % interface_name
    with _connect(router) as conn:
        raw = conn.send_command(cmd)
        if "%" in raw or "invalid" in raw.lower():
            return [], []
        ip_info = conn.send_command(cmd, use_textfsm=True)
        if isinstance(ip_info, str):
            raise RuntimeError("could not parse 'show ip interface'")
        descriptions = conn.send_command(
            "show interfaces description", use_textfsm=True
        )
        if isinstance(descriptions, str):
            raise RuntimeError("could not parse 'show interfaces description'")
        return ip_info, descriptions


def _default_delete(router, interface_name):
    # Safety: the real path only ever deletes Loopback interfaces.
    common.loopback_number(interface_name)

    ip_info, descriptions = _default_get(router, interface_name)
    if _normalize(interface_name, ip_info, descriptions) is None:
        return "not_found"

    with _connect(router) as conn:
        output = conn.send_config_set(["no interface %s" % interface_name])
    if "%" in output:
        raise RuntimeError("router rejected 'no interface'")

    ip_info, descriptions = _default_get(router, interface_name)
    if _normalize(interface_name, ip_info, descriptions) is not None:
        raise RuntimeError("interface still present after delete")
    return "deleted"


def get_interface_state(
    router,
    interface_name,
    netmiko_get=None,
):
    """Return normalized interface status using Netmiko + TextFSM."""
    get = netmiko_get or _default_get
    try:
        ip_info, descriptions = get(router, interface_name)
        iface = _normalize(interface_name, ip_info, descriptions)
        if iface is None:
            return common.not_found()
        return {"status": "ok", "result": "found", "interface": iface}
    except Exception as exc:
        logger.exception("netmiko status failed")
        return common.error(common.classify_exception(exc))


def delete_interface(
    router,
    interface_name,
    netmiko_delete=None,
):
    """Delete an interface using Netmiko."""
    delete = netmiko_delete or _default_delete
    try:
        outcome = delete(router, interface_name)
    except Exception as exc:
        logger.exception("netmiko delete failed")
        return common.error(common.classify_exception(exc))
    if outcome == "deleted":
        return {"status": "ok", "result": "deleted"}
    if outcome == "not_found":
        return common.not_found()
    return common.error("backend_failed")