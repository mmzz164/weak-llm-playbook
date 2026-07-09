"""default_probe.py / spec_holes.py 共通のLLMクライアント。
任意のエンドポイントを測定対象にできる:
  - api="openai"    : POST {base}/v1/chat/completions (vLLM / llama.cpp / OpenAI / ollama等)
  - api="anthropic" : POST {base}/v1/messages (Anthropic API / claude-code-router等)
認証: key引数 > PROBE_API_KEY > ANTHROPIC_API_KEY > OPENAI_API_KEY の順で解決。
      openaiは Authorization: Bearer、anthropicは x-api-key + Authorization: Bearer の両方を送る。
モデル差異の自動吸収:
  - openai: chat_template_kwargs(enable_thinking)非対応なら外して再試行(以後は送らない)
  - anthropic: temperature非対応モデル(Fable5/Opus4.7+等)は400を検知して外し再試行
"""
import json, os, urllib.request, urllib.error


class LLMClient:
    def __init__(self, model, base, api="openai", key=None, think=False):
        self.model = model
        self.base = base.rstrip("/")
        self.api = api
        self.key = (key or os.environ.get("PROBE_API_KEY")
                    or os.environ.get("ANTHROPIC_API_KEY")
                    or os.environ.get("OPENAI_API_KEY"))
        self.think = think
        self._no_ctk = False    # openai: chat_template_kwargs 非対応を記憶
        self._no_temp = False   # anthropic: temperature 非対応を記憶

    def _post(self, path, payload, headers):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **headers})
        return json.load(urllib.request.urlopen(req, timeout=300))

    def chat(self, prompt, temperature=0.7, max_tokens=400):
        """1往復して本文テキストを返す。"""
        if self.api == "anthropic":
            return self._anthropic(prompt, temperature, max_tokens)
        return self._openai(prompt, temperature, max_tokens)

    # --- OpenAI chat completions 形式 ---
    def _openai(self, prompt, temperature, max_tokens):
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        body = {"model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "temperature": temperature}
        if not self._no_ctk:
            try:
                r = self._post("/v1/chat/completions",
                               {**body, "chat_template_kwargs": {"enable_thinking": self.think}},
                               headers)
                return r["choices"][0]["message"].get("content") or ""
            except Exception:
                self._no_ctk = True   # 非対応サーバー: 以後は素のリクエスト
        r = self._post("/v1/chat/completions", body, headers)
        return r["choices"][0]["message"].get("content") or ""

    # --- Anthropic Messages 形式 ---
    def _anthropic(self, prompt, temperature, max_tokens):
        if not self.key:
            raise RuntimeError("api=anthropic には --key か ANTHROPIC_API_KEY 等が必要")
        headers = {"x-api-key": self.key,
                   "Authorization": f"Bearer {self.key}",
                   "anthropic-version": "2023-06-01"}
        body = {"model": self.model, "max_tokens": max(max_tokens, 64),
                "messages": [{"role": "user", "content": prompt}]}
        if not self._no_temp and temperature is not None:
            body["temperature"] = temperature
        try:
            r = self._post("/v1/messages", body, headers)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code == 400 and "temperature" in msg and "temperature" in body:
                self._no_temp = True   # Fable5/Opus4.7+等: temperatureを外して再試行
                body.pop("temperature")
                r = self._post("/v1/messages", body, headers)
            else:
                raise RuntimeError(f"HTTP {e.code}: {msg}") from e
        return "".join(b.get("text", "") for b in r.get("content", [])
                       if b.get("type") == "text")
