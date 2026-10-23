"""Shared helpers for the IPA2026 backends (errors, exception mapping, IPv4)."""
import ipaddress
import os
import re


def error(code):
    return {"status": "error", "result": code}


def not_found():
    return {"status": "ok", "result": "not_found", "interface": None}


_AUTH_HINTS = ("authentication", "permission", "unauthorized", "authorization")
_CONN_HINTS = (
    "timeout",
    "connectionerror",
    "connectionrefused",
    "unreachable",
    "sshexception",
    "ssherror",
    "novalidconnections",
    "sessionclose",
    "gaierror",
)


def classify_exception(exc):
    """Map any transport exception to a backend error code."""
    if isinstance(exc, PermissionError):
        return "authentication_failed"
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return "connection_failed"
    # Library exceptions (requests, ncclient, paramiko, netmiko, ...) are
    # recognised by class name so those libraries need not be imported.
    names = " ".join(c.__name__.lower() for c in type(exc).__mro__)
    if any(h in names for h in _AUTH_HINTS):
        return "authentication_failed"
    if any(h in names for h in _CONN_HINTS):
        return "connection_failed"
    return "backend_failed"


def credentials():
    user = os.environ.get("ROUTER_USER")
    password = os.environ.get("ROUTER_PASS")
    if not user or not password:
        raise PermissionError("ROUTER_USER / ROUTER_PASS are not set")
    return user, password


def loopback_number(name):
    """'Loopback123' -> '123'. Raises ValueError for any other name."""
    m = re.fullmatch(r"Loopback(\d+)", str(name))
    if not m:
        raise ValueError("not a Loopback interface name: %r" % (name,))
    return m.group(1)


def split_cidr(ipv4):
    """'172.23.123.1/32' -> ('172.23.123.1', '255.255.255.255')."""
    iface = ipaddress.IPv4Interface(ipv4)
    return str(iface.ip), str(iface.netmask)


def to_cidr(ip, mask):
    """Combine an address with a netmask / prefix length into CIDR text."""
    mask = str(mask).strip().lstrip("/")
    if "." in mask:
        prefix = ipaddress.IPv4Network("0.0.0.0/" + mask).prefixlen
    else:
        prefix = int(mask)
        if not 0 <= prefix <= 32:
            raise ValueError("bad prefix length")
    ipaddress.IPv4Address(str(ip).strip())
    return "%s/%d" % (str(ip).strip(), prefix)