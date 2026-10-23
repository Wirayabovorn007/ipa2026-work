import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from app.backends import common
from app.backends.planning import plan_interface as _plan


def _filter_xml(name):
    return (
        '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">'
        "<interface><name>%s</name></interface></interfaces>" % escape(str(name))
    )


def _config_xml(desired):
    number = common.loopback_number(desired["name"])
    address, mask = common.split_cidr(desired["ipv4"])
    description = desired.get("description")
    parts = [
        '<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" '
        'xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">',
        '<native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">',
        '<interface><Loopback nc:operation="replace">',
        "<name>%s</name>" % number,
    ]
    if description is not None:
        parts.append("<description>%s</description>" % escape(str(description)))
    parts.append(
        "<ip><address><primary><address>%s</address><mask>%s</mask>"
        "</primary></address></ip>" % (address, mask)
    )
    if desired["admin_state"] == "down":
        parts.append("<shutdown/>")
    parts.append("</Loopback></interface></native></config>")
    return "".join(parts)


def _default_get_config(router, filter_xml):
    from ncclient import manager

    user, password = common.credentials()
    with manager.connect(
        host=router,
        port=830,
        username=user,
        password=password,
        hostkey_verify=False,
        look_for_keys=False,
        allow_agent=False,
        timeout=30,
    ) as m:
        return m.get_config(source="running", filter=("subtree", filter_xml)).data_xml


def _default_edit_config(router, config_xml):
    from ncclient import manager

    user, password = common.credentials()
    with manager.connect(
        host=router,
        port=830,
        username=user,
        password=password,
        hostkey_verify=False,
        look_for_keys=False,
        allow_agent=False,
        timeout=30,
    ) as m:
        m.edit_config(target="running", config=config_xml)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child(elem, name):
    for c in elem:
        if _local(c.tag) == name:
            return c
    return None


def _text(elem):
    return None if elem is None or elem.text is None else elem.text.strip()


def _parse(xml_text, requested_name):
    """Return a normalized interface dict, or None if absent."""
    root = ET.fromstring(xml_text)
    candidates = [e for e in root.iter() if _local(e.tag) == "interface"]
    chosen = None
    for cand in candidates:
        if _text(_child(cand, "name")) == requested_name:
            chosen = cand
            break
    if chosen is None:
        return None

    ipv4 = None
    ip_node = _child(chosen, "ipv4")
    if ip_node is not None:
        addr = _child(ip_node, "address")
        if addr is not None:
            ip = _text(_child(addr, "ip"))
            mask = _text(_child(addr, "netmask")) or _text(
                _child(addr, "prefix-length")
            )
            if ip and mask:
                ipv4 = common.to_cidr(ip, mask)

    enabled = _text(_child(chosen, "enabled"))
    up = True if enabled is None else enabled.lower() == "true"
    return {
        "name": requested_name,
        "ipv4": ipv4,
        "description": _text(_child(chosen, "description")),
        "admin_state": "up" if up else "down",
    }


def get_interface_state(
    router,
    interface_name,
    netconf_get_config=None,
):
    """Return normalized interface status using NETCONF."""
    get = netconf_get_config or _default_get_config
    try:
        xml_text = get(router, _filter_xml(interface_name))
        iface = _parse(xml_text, interface_name)
        if iface is None:
            return common.not_found()
        return {"status": "ok", "result": "found", "interface": iface}
    except Exception as exc:
        return common.error(common.classify_exception(exc))


def plan_interface(
    router,
    desired_interface,
    netconf_get_config=None,
):
    """Return create/update/no_change plan using NETCONF status."""
    return _plan(
        router,
        desired_interface,
        lambda r, n: get_interface_state(
            r, n, netconf_get_config=netconf_get_config
        ),
    )


def apply_interface(
    router,
    desired_interface,
    netconf_edit_config=None,
):
    """Apply complete desired interface state using NETCONF."""
    edit = netconf_edit_config or _default_edit_config
    try:
        edit(router, _config_xml(desired_interface))
        return {"status": "ok", "result": "applied"}
    except Exception as exc:
        return common.error(common.classify_exception(exc))