"""Chat clients for every model in configs/models.yaml.

The request body carries the messages and nothing else: temperature, top-p, seed and tools are never sent. `max_tokens`, `reasoning_effort` and JSON mode are sent only when configured or requested (paper Appendix E).
"""

import json
import os
import random
import re
import threading
import time
from pathlib import Path

import httpx

from ideataste.catalog import model_config

MAX_RETRIES = 5  # failed attempts before giving up (2**n s back-off)
MAX_RATE_LIMIT_RETRIES = 8  # 429s get their own, longer budget
TIMEOUT_SECONDS = 180


class EmptyReply(RuntimeError):
    """HTTP 200 without message content."""


class LLMError(RuntimeError):
    pass


class _RetryingClient:
    """Retry policy shared by all clients: transient errors back off 2**n seconds, rate limits back off up to 60 s on a separate budget."""

    fatal_status = ()  # HTTP statuses not worth retrying

    def __init__(self, config, log_path=None):
        self.config = config
        self.api_key = os.environ.get(config["api_key_env"], "")
        if not self.api_key and not config.get("base_url", "").startswith("http://localhost"):
            raise LLMError(f"{config['api_key_env']} is not set: add it to .env (see .env.example) or export it to call {config['name']}")
        self.log_path = Path(log_path) if log_path else None
        self._log_lock = threading.Lock()

    def chat(self, system, user, json_mode=False, tag=None):
        """-> (reply text, {"reasoning", "usage", "finish_reason"})."""
        body = self._body(system, user, json_mode)
        errors, failures, throttles, empties = [], 0, 0, 0
        while failures < MAX_RETRIES:
            try:
                reply, meta = self._send(body)
                self._log(tag, system, user, reply, meta, errors)
                return reply, meta
            except Exception as error:  # noqa: BLE001 - every attempt is recorded and re-raised at the end
                errors.append(f"{type(error).__name__}: {error}")
                status = getattr(getattr(error, "response", None), "status_code", None)
                if isinstance(error, EmptyReply):
                    empties += 1
                    self._on_empty_reply(body, empties)
                if status == 429 and throttles < MAX_RATE_LIMIT_RETRIES:
                    throttles += 1
                    time.sleep(min(60, 5 * 2 ** min(throttles, 4)) + random.uniform(0, 5))
                    continue
                if status in self.fatal_status:
                    break
                failures += 1
                time.sleep(2**failures)
        self._log(tag, system, user, None, None, errors)
        raise LLMError(f"{self.config['name']} failed after {len(errors)} attempts: " + " | ".join(errors))

    def _on_empty_reply(self, body, n_empty):
        """After two empty replies, lower reasoning effort for this call only if the model config names a fallback (Gemini routes some thinking output into a filtered function-call channel)."""
        fallback = self.config.get("fallback_reasoning_effort")
        if fallback and n_empty >= 2 and body.get("reasoning_effort") not in (None, fallback):
            body["reasoning_effort"] = fallback

    def _log(self, tag, system, user, reply, meta, errors):
        if self.log_path is None:
            return
        row = {"tag": tag, "model": self.config["model"], "system": system, "user": user, "reply": reply, **(meta or {}), "failed_attempts": errors}
        with self._log_lock, self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class OpenAICompatibleClient(_RetryingClient):
    """POST {base_url}/chat/completions — DeepSeek, OpenAI, Anthropic, Gemini, IFM, vLLM."""

    def _body(self, system, user, json_mode):
        body = {"model": self.config["model"], "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.config.get("max_tokens"):
            body["max_tokens"] = self.config["max_tokens"]
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.config.get("reasoning_effort"):
            body["reasoning_effort"] = self.config["reasoning_effort"]
        return body

    def _send(self, body):
        response = httpx.post(f"{self.config['base_url']}/chat/completions", json=body, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]
        if message.get("content") is None:
            raise EmptyReply(f"finish_reason={choice.get('finish_reason')}")
        return message["content"], {"reasoning": message.get("reasoning_content") or message.get("reasoning"), "usage": data.get("usage"), "finish_reason": choice.get("finish_reason")}


class BedrockClient(_RetryingClient):
    """AWS Bedrock Converse API (Llama 4 Scout has no chat-completions endpoint there)."""

    fatal_status = (400, 401, 403, 404)

    def _body(self, system, user, json_mode):
        if json_mode:
            raise LLMError(f"{self.config['name']} has no JSON mode")
        return {"messages": [{"role": "user", "content": [{"text": user}]}], "system": [{"text": system}], "inferenceConfig": {"maxTokens": self.config["max_tokens"]}}

    def _send(self, body):
        url = f"https://bedrock-runtime.{self.config['region']}.amazonaws.com/model/{self.config['model']}/converse"
        response = httpx.post(url, json=body, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        blocks = (data.get("output") or {}).get("message", {}).get("content") or []
        return "".join(b.get("text", "") for b in blocks), {"reasoning": None, "usage": data.get("usage"), "finish_reason": data.get("stopReason")}


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_json(reply):
    """The JSON object in a model reply, tolerating code fences and surrounding prose."""
    match = _JSON_OBJECT.search(reply or "")
    if not match:
        raise json.JSONDecodeError("no JSON object", reply or "", 0)
    return json.loads(match.group(0))


def make_client(model, log_path=None):
    config = model_config(model)
    client_class = BedrockClient if config.get("provider") == "bedrock" else OpenAICompatibleClient
    return client_class(config, log_path)
