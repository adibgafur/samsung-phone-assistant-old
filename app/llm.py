"""Thin wrapper around the Groq chat-completions API."""
from groq import Groq, GroqError

from app.config import GROQ_API_KEY, GROQ_MODEL


class LLMError(RuntimeError):
    pass


def get_available_models(api_key: str | None = None, base_url: str | None = None) -> list[str]:
    """Fetch all accessible chat model IDs for this specific API key."""
    clean_url = (base_url or "").strip() or None
    clean_key = (api_key or "").strip() or ("localhost" if clean_url else "")
    if not clean_key and not clean_url:
        return []
    try:
        kwargs = {"api_key": clean_key or "localhost"}
        if clean_url:
            kwargs["base_url"] = clean_url
        client = Groq(**kwargs)
        res = client.models.list()
        all_models = [m.id for m in getattr(res, "data", [])]
        chat_models = [
            m for m in all_models
            if not any(skip in m.lower() for skip in ["whisper", "guard", "orpheus", "safeguard", "embed", "tts"])
        ]
        return chat_models or all_models
    except Exception:
        return []


class GroqLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        self.model = (model or "").strip() or GROQ_MODEL
        self.base_url = (base_url or "").strip() or None
        # If localhost base_url is used, an api_key is not strictly required by local runners like Ollama
        resolved_key = (api_key.strip() if api_key else None) or (GROQ_API_KEY if not self.base_url else "localhost")
        self._api_key = resolved_key or ("localhost" if self.base_url else None)
        self._client: Groq | None = None

    @property
    def api_key(self) -> str | None:
        return self._api_key

    @property
    def client(self) -> Groq:
        if self._client is None:
            if not self._api_key and not self.base_url:
                raise LLMError("GROQ_API_KEY is not set. Please provide it in the front-end or set it in your .env file.")
            kwargs = {"api_key": self._api_key or "localhost"}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = Groq(**kwargs)
        return self._client

    def chat(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 900) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except GroqError as exc:
            if "model_not_found" in str(exc):
                # Dynamically retrieve models that THIS key actually has access to
                models = get_available_models(self.api_key, self.base_url)
                if models and models[0] != self.model:
                    self.model = models[0]
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                else:
                    raise LLMError(f"LLM request failed: {exc}. Available models: {', '.join(models[:5]) if models else 'None'}") from exc
            else:
                raise LLMError(f"LLM request failed: {exc}") from exc
        return (resp.choices[0].message.content or "").strip()


def verify_api_key(api_key: str | None = None, model: str | None = None, base_url: str | None = None) -> dict:
    """Verifies an API key or localhost endpoint by testing connectivity and model access."""
    clean_url = (base_url or "").strip() or None
    clean_key = (api_key or "").strip() or ("localhost" if clean_url else "")
    
    if not clean_key and not clean_url:
        return {"valid": False, "error": "API key cannot be empty unless using a local host endpoint"}
    try:
        kwargs = {"api_key": clean_key or "localhost"}
        if clean_url:
            kwargs["base_url"] = clean_url
        client = Groq(**kwargs)

        # Retrieve models actually assigned to this key
        available = get_available_models(api_key=clean_key, base_url=clean_url)
        chosen_model = (model or "").strip()
        if not chosen_model or (available and chosen_model not in available):
            chosen_model = available[0] if available else (model or GROQ_MODEL)

        client.chat.completions.create(
            model=chosen_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )

        return {
            "valid": True,
            "model": chosen_model,
            "base_url": clean_url,
            "available_models": available,
        }
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


