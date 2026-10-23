"""Part 4: minimal Webex REST client."""

import os
from urllib.parse import quote

import requests

WEBEX_API_BASE = 'https://webexapis.com/v1'

_TIMEOUT = 10


class WebexClient:
    def __init__(self, token=None, session=None):
        token = token or os.environ.get("WEBEX_BOT_TOKEN")
        if not token:
            raise PermissionError("WEBEX_BOT_TOKEN is not set")
        self.token = token
        self.session = session if session is not None else requests.Session()

    @property
    def headers(self):
        return {"Authorization": "Bearer %s" % self.token}

    def get_message(self, message_id):
        resp = self.session.get(
            "%s/messages/%s" % (WEBEX_API_BASE, quote(str(message_id), safe="")),
            headers=self.headers,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def download_file(self, file_url):
        resp = self.session.get(
            file_url,
            headers=self.headers,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.content

    def send_message(self, room_id, text):
        resp = self.session.post(
            "%s/messages" % WEBEX_API_BASE,
            headers=self.headers,
            json={"roomId": room_id, "text": text},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()