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


def _strip_think(text):
    """qwen3等の思考ブロックを除去する。閉じていない(=max_tokensで切断された)思考は
    末尾まで落とす。全ツールの出力パースをollama等の思考モデルに対して頑健にする。"""
    t = _re.sub(r"<think>.*?</think>\s*", "", text, flags=_re.S)
    i = t.find("<think>")
    return t[:i] if i >= 0 else t


def _order_models(models):
    """chat向きを先頭へ(embedding系を後ろへ)。ollamaはpull済み全モデルを列挙するため、
    先頭が会話不能なモデルだと自動検出が事故る。元の順序は安定に保つ。"""
    chat = [m for m in models if "embed" not in m.lower()]
    rest = [m for m in models if "embed" in m.lower()]
    return chat + rest


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
        raise RuntimeError(f"model auto-detection failed ({base}/v1/models): {e}. Specify the model explicitly") from e
    if not models:
        raise RuntimeError(f"{base}/v1/models returned no models. Specify the model explicitly")
    return _order_models(models)


class LLMClient:
    def __init__(self, model, base, api="openai", key=None, think=False):
        self.model = model
        self.base = base.rstrip("/")
        self.api = api
        self.key = _resolve_key(key)
        self.think = think
        self.last_usage = None  # 直近chat()の {"in": prompt_tokens, "out": completion_tokens}
        self._no_ctk = False    # openai: chat_template_kwargs 非対応を記憶
        self._no_temp = False   # anthropic: temperature 非対応を記憶
        self._soft_nothink = False  # openai: /no_think ソフトスイッチ常用を記憶(ollama等)

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
    def _finish_openai(self, r):
        u = r.get("usage") or {}
        self.last_usage = {"in": u.get("prompt_tokens"), "out": u.get("completion_tokens")}
        return r["choices"][0]["message"].get("content") or ""

    def _openai(self, prompt, temperature, max_tokens):
        if self._soft_nothink:
            prompt = prompt + "\n/no_think"
        raw = self._openai_raw(prompt, temperature, max_tokens)
        text = _strip_think(raw)
        if self.think or text.strip():
            return text
        if "<think>" in raw and not self._soft_nothink:
            # 思考が生成予算を食い潰して本文が空(ollama等は chat_template_kwargs を
            # 黙って無視する)。Qwen系のソフトスイッチ /no_think で再試行し、効けば以後常用。
            self._soft_nothink = True
            return _strip_think(self._openai_raw(prompt + "\n/no_think", temperature, max_tokens))
        return text

    def _openai_raw(self, prompt, temperature, max_tokens):
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        body = {"model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "temperature": temperature}
        if not self._no_ctk:
            try:
                r = self._post("/v1/chat/completions",
                               {**body, "chat_template_kwargs": {"enable_thinking": self.think}},
                               headers)
                return self._finish_openai(r)
            except Exception:
                self._no_ctk = True   # 非対応サーバー: 以後は素のリクエスト
        r = self._post("/v1/chat/completions", body, headers)
        return self._finish_openai(r)

    # --- Anthropic Messages 形式 ---
    def _anthropic(self, prompt, temperature, max_tokens):
        if not self.key:
            raise RuntimeError("api=anthropic requires --key or ANTHROPIC_API_KEY (etc.)")
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
        u = r.get("usage") or {}
        self.last_usage = {"in": u.get("input_tokens"), "out": u.get("output_tokens")}
        return "".join(b.get("text", "") for b in r.get("content", [])
                       if b.get("type") == "text")
