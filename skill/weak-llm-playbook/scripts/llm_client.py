"""default_probe.py / spec_holes.py 共通のLLMクライアント。
任意のエンドポイントを測定対象にできる:
  - api="openai"    : POST {base}/v1/chat/completions (vLLM / llama.cpp / OpenAI / ollama等)
  - api="anthropic" : POST {base}/v1/messages (Anthropic API / claude-code-router等)
認証: key引数 > PROBE_API_KEY > ANTHROPIC_API_KEY > OPENAI_API_KEY の順で解決。
      openaiは Authorization: Bearer、anthropicは x-api-key + Authorization: Bearer の両方を送る。
モデル差異の自動吸収:
  - openai: chat_template_kwargs(enable_thinking)非対応なら外して再試行(以後は送らない)
  - anthropic: temperature非対応モデル(Fable5/Opus4.7+等)は400を検知して外し再試行
detect_model(base): GET /v1/models で配信中モデルを自動検出(model引数の省略用)。
"""
import json, os, re as _re, urllib.request, urllib.error


def _resolve_key(key=None):
    return (key or os.environ.get("PROBE_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("OPENAI_API_KEY"))


def find_json(text):
    """テキストからJSON値を抽出してparse(生/```フェンス/前後に説明文があっても拾う)。失敗はNone。"""
    t = text.strip()
    m = _re.search(r"```(?:json)?\s*(.*?)```", t, _re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    for oc, cc in (("{", "}"), ("[", "]")):
        i = t.find(oc)
        if i < 0:
            continue
        depth = 0
        for j in range(i, len(t)):
            if t[j] == oc:
                depth += 1
            elif t[j] == cc:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[i:j + 1])
                    except Exception:
                        break
    return None


def detect_model(base, key=None):
    """GET {base}/v1/models で配信中モデルのID一覧を返す(OpenAI互換サーバー用)。
    vLLM/llama.cpp/ollama は単一〜少数モデルなので、呼び出し側は先頭を既定に使える。"""
    key = _resolve_key(key)
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/models",
        headers={"Authorization": f"Bearer {key}"} if key else {})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=10))
        models = [m["id"] for m in r.get("data", []) if m.get("id")]
    except Exception as e:
        raise RuntimeError(f"モデル自動検出に失敗 ({base}/v1/models): {e}。model引数を明示してください") from e
    if not models:
        raise RuntimeError(f"{base}/v1/models が空。model引数を明示してください")
    return models


class LLMClient:
    def __init__(self, model, base, api="openai", key=None, think=False):
        self.model = model
        self.base = base.rstrip("/")
        self.api = api
        self.key = _resolve_key(key)
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
