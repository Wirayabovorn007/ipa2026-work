"""Part 4: Webex webhook service."""

import json

import logging

import os

from concurrent.futures import ThreadPoolExecutor

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from tempfile import TemporaryDirectory

from app.integration import process_request

from app.webex_client import WEBEX_API_BASE, WebexClient

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 1_000_000


def _error(code):
    return {"status": "error", "result": code}


class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def _is_self(self, person_id):
        return bool(self.bot_person_id) and person_id == self.bot_person_id

    def _run_processor(self, mentioned_people, files):
        """Return the response dict; never raises for processing problems."""
        try:
            if not files:
                return self.processor(mentioned_people, None, self.bot_person_id)
            content = self.client.download_file(files[0])
            # The temporary directory (and file) is removed even if
            # processing raises.
            with TemporaryDirectory() as tmp:
                path = Path(tmp) / "request.yaml"
                path.write_bytes(content)
                return self.processor(
                    mentioned_people, path, self.bot_person_id
                )
        except Exception:
            logger.exception("request processing failed")
            return _error("backend_failed")

    def handle_event(self, event):
        if not isinstance(event, dict):
            return None
        if event.get("resource") != "messages" or event.get("event") != "created":
            return None
        data = event.get("data")
        if not isinstance(data, dict):
            return None
        message_id = data.get("id")
        if not isinstance(message_id, str) or not message_id:
            return None

        # Ignore our own messages before spending an API call on them.
        if self._is_self(data.get("personId")):
            return None

        message = self.client.get_message(message_id)
        if not isinstance(message, dict):
            return None
        # Also check the author of the fetched message (reply-loop guard).
        if self._is_self(message.get("personId")):
            return None

        room_id = message.get("roomId") or data.get("roomId")
        if not room_id:
            return None

        files = message.get("files")
        if not isinstance(files, list):
            files = []
        mentioned_people = message.get("mentionedPeople") or []

        if len(files) > 1:
            response = _error("multiple_attachments")
        else:
            response = self._run_processor(mentioned_people, files)

        self.client.send_message(room_id, json.dumps(response))
        return response


def make_http_handler(submit_event):
    class WebhookHTTPHandler(BaseHTTPRequestHandler):
        server_version = "IPA2026Webhook/1.0"

        def log_message(self, format, *args):
            logger.info("%s - %s", self.address_string(), format % args)

        def _send_json(self, code, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _drain(self, length, limit=10 * MAX_BODY_BYTES):
            remaining = min(max(length, 0), limit)
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)

        def _path(self):
            return self.path.split("?", 1)[0]

        def do_GET(self):
            if self._path() == "/health":
                self._send_json(200, {"status": "ok", "result": "healthy"})
            else:
                self._send_json(404, _error("not_found"))

        def do_POST(self):
            if self._path() != "/webhook":
                self._send_json(404, _error("not_found"))
                return

            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length)
            except (TypeError, ValueError):
                length = 0
            if length < 1 or length > MAX_BODY_BYTES:
                # Read (and discard) a reasonably sized body first so the
                # client can finish sending and actually see the 400.
                self._drain(length)
                self._send_json(400, _error("invalid_event"))
                return

            body = self.rfile.read(length)
            try:
                event = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                event = None
            if not isinstance(event, dict):
                self._send_json(400, _error("invalid_event"))
                return

            try:
                submit_event(event)
            except Exception:
                logger.exception("could not queue event")
                self._send_json(500, _error("backend_failed"))
                return
            self._send_json(200, {"status": "ok", "result": "accepted"})

    return WebhookHTTPHandler


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", "8000"))

    # The Webex client and bot identity are created lazily so the HTTP
    # server (and /health) can start even when WEBEX_BOT_TOKEN is not set,
    # as in the offline image smoke test.
    state = {"handler": None}

    def get_handler():
        if state["handler"] is None:
            client = WebexClient()
            resp = client.session.get(
                "%s/people/me" % WEBEX_API_BASE,
                headers=client.headers,
                timeout=10,
            )
            resp.raise_for_status()
            bot_person_id = resp.json()["id"]
            state["handler"] = WebexEventHandler(client, bot_person_id)
            logger.info("bot identity resolved")
        return state["handler"]

    def work(event):
        try:
            get_handler().handle_event(event)
        except Exception:
            logger.exception("event handling failed")

    # One worker => router requests are processed strictly one at a time,
    # and the HTTP acknowledgement never waits for the router.
    executor = ThreadPoolExecutor(max_workers=1)

    def submit_event(event):
        executor.submit(work, event)

    server = ThreadingHTTPServer((host, port), make_http_handler(submit_event))
    logger.info("webhook listening on %s:%s", host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        executor.shutdown(wait=False)


if __name__ == "__main__":
    main()