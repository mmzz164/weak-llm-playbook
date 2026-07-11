#!/usr/bin/env python3
"""Offline demo model: an OpenAI-compatible mock that acts like a weak LLM.

It alternates between two plausible implementations of top_n — the classic
spec hole ("top n" by value? or just the first n?) — unless the prompt
already contains a pinned behavior contract, in which case it obeys the pin
(like a real model reading a now-unambiguous spec). Deterministic, localhost
only, no GPU.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "18990"))
A = "```python\ndef top_n(lst, n):\n    return sorted(lst, reverse=True)[:n]\n```"
B = "```python\ndef top_n(lst, n):\n    return lst[:n]\n```"
state = {"n": 0}


class H(BaseHTTPRequestHandler):
    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self._send({"object": "list", "data": [{"id": "demo-weak-model", "object": "model"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        prompt = self.rfile.read(n).decode("utf-8", "replace")
        if "[Behavior contract" in prompt or "[挙動の固定" in prompt:
            content = A  # the spec is unambiguous now -> consistent behavior
        else:
            content = A if state["n"] % 2 == 0 else B
            state["n"] += 1
        self._send({"choices": [{"message": {"role": "assistant", "content": content}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20}})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
