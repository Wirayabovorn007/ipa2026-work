import json
import os
import subprocess
from pathlib import Path

from app.backends import common

_PLAYBOOK = Path(__file__).resolve().parents[2] / "ansible" / "apply_interface.yml"


def _default_run_playbook(variables):
    playbook = os.environ.get("IPA_PLAYBOOK", str(_PLAYBOOK))
    env = dict(os.environ, ANSIBLE_HOST_KEY_CHECKING="False")
    common.credentials()  # fail early with authentication_failed if unset
    proc = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            variables["router"] + ",",
            playbook,
            "-e",
            json.dumps(variables),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    if proc.returncode == 0:
        return 0
    text = (proc.stdout + proc.stderr).lower()
    if proc.returncode == 4 or "unreachable" in text:
        if any(
            s in text
            for s in ("authentication", "permission denied", "incorrect password")
        ):
            raise PermissionError("ansible authentication failed")
        raise ConnectionError("ansible could not reach router")
    raise RuntimeError("ansible playbook failed")


def apply_interface(
    router,
    desired_interface,
    run_playbook=None,
):
    """Apply complete desired interface state using Ansible."""
    run = run_playbook or _default_run_playbook
    try:
        address, mask = common.split_cidr(desired_interface["ipv4"])
        variables = {
			"router": router,
			"interface_name": desired_interface["name"],
			"name": desired_interface["name"],
			"ipv4": desired_interface["ipv4"],
			"ipv4_address": address,
			"netmask": mask,
			"description": desired_interface["description"],
			"admin_state": desired_interface["admin_state"],
			"shutdown": desired_interface["admin_state"] == "down",
		}
        result = run(variables)
        if result is False or (
            isinstance(result, int) and not isinstance(result, bool) and result != 0
        ):
            return common.error("backend_failed")
        return {"status": "ok", "result": "applied"}
    except Exception as exc:
        return common.error(common.classify_exception(exc))