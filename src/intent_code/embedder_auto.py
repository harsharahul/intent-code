"""Pick an embedder automatically.

Prefer a local Ollama embedding model (better code semantics) when the server is
reachable *and* the model is actually pulled; otherwise fall back to intent-db's
zero-dependency hashing embedder. The probe is deliberately cheap and
short-timeout so we never hang when Ollama is absent.

Detection re-runs every time an index is opened, so a store built while Ollama
was down is not stuck on the fallback forever: the mismatch is reported, and
`intent-code index --full` adopts the better embedder.

Override with the INTENT_CODE_EMBEDDER environment variable.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Callable, Iterator

HASHING_SPEC = "hashing:dim=512"
DEFAULT_OLLAMA_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

#: the /api/tags probe runs on every open, so keep it near-instant
PROBE_TIMEOUT = 0.5
#: an embedding model is a few hundred MB; give the download room
PULL_TIMEOUT = 1800.0

ProgressFn = Callable[[str], None]


def ollama_models(
    host: str = DEFAULT_OLLAMA_HOST, timeout: float = PROBE_TIMEOUT
) -> list[str] | None:
    """Names of the models the server holds locally, or None if unreachable.

    None and [] are different answers: unreachable means fall back, while up but
    without the model means we can offer to pull it.
    """
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            payload = json.loads(resp.read())
    except Exception:
        return None
    names = []
    for entry in payload.get("models") or []:
        name = entry.get("name") or entry.get("model")
        if name:
            names.append(name)
    return names


def has_model(models: list[str], wanted: str) -> bool:
    """True if `wanted` is present, comparing names without their tag.

    Ollama reports `nomic-embed-text:latest` for what you pulled as plain
    `nomic-embed-text`, so an exact string match would miss it.
    """
    base = wanted.partition(":")[0]
    return any(name == wanted or name.partition(":")[0] == base for name in models)


def ollama_available(
    host: str = DEFAULT_OLLAMA_HOST, timeout: float = PROBE_TIMEOUT
) -> bool:
    """True when an Ollama server answers, whichever models it happens to hold."""
    return ollama_models(host, timeout) is not None


def _progress_line(event: dict) -> tuple[str, tuple]:
    """Render one /api/pull event, plus a key used to suppress repeats."""
    status = str(event.get("status", ""))
    total = event.get("total")
    completed = event.get("completed")
    if total and completed:
        pct = 100.0 * completed / total
        # Report per decile: a byte-level stream would flood the terminal.
        return f"{status} {pct:.0f}%", (status, int(pct // 10))
    return status, (status, None)


def pull_model(
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    on_progress: ProgressFn | None = None,
    timeout: float = PULL_TIMEOUT,
) -> bool:
    """Ask Ollama to pull `model`. Returns True on success.

    Streamed, so a several-hundred-MB download reports progress instead of
    stalling silently. Never raises: a failed pull means we fall back, which is
    a degraded result rather than an error.
    """
    # `model` is the current field name, `name` the long-standing alias; sending
    # both keeps older Ollama servers working.
    body = json.dumps({"model": model, "name": model, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/pull", data=body, headers={"Content-Type": "application/json"}
    )
    last_key: tuple | None = None
    succeeded = False
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("error"):
                    if on_progress:
                        on_progress(f"pull failed: {event['error']}")
                    return False
                message, key = _progress_line(event)
                if message and key != last_key:
                    last_key = key
                    if on_progress:
                        on_progress(message)
                if event.get("status") == "success":
                    succeeded = True
    except Exception as e:
        if on_progress:
            on_progress(f"pull failed: {e}")
        return False
    if succeeded:
        return True
    # Older servers do not always emit a final "success"; trust the tag list.
    return has_model(ollama_models(host) or [], model)


def pull_allowed(default: bool = False) -> bool:
    """Whether an automatic pull is permitted.

    Callers pass the context default (true for an explicit index, false for a
    query-time refresh); INTENT_CODE_AUTO_PULL overrides in either direction.
    """
    env = os.environ.get("INTENT_CODE_AUTO_PULL")
    if env is None:
        return default
    return env.strip().lower() not in ("0", "false", "no", "off")


def describe_auto(
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    allow_pull: bool = False,
    on_progress: ProgressFn | None = None,
) -> tuple[str, str | None]:
    """Return (embedder_spec, warning_or_None) for the auto-detected embedder."""
    override = os.environ.get("INTENT_CODE_EMBEDDER")
    if override:
        return override, None

    models = ollama_models(host)
    if models is None:
        return (
            HASHING_SPEC,
            "No Ollama server reachable; using the zero-dependency hashing "
            "embedder. Conceptual search is much weaker (lexical only). Start "
            f"Ollama, then run `intent-code index --full` to switch to {model}.",
        )
    if has_model(models, model):
        return f"ollama:model={model}", None

    if pull_allowed(allow_pull):
        if on_progress:
            on_progress(f"{model} is not pulled yet; fetching it once")
        if pull_model(model, host, on_progress=on_progress):
            return f"ollama:model={model}", None
        return (
            HASHING_SPEC,
            f"Ollama is running but pulling {model} failed; using the hashing "
            f"embedder (lexical only). Run `ollama pull {model}` yourself, then "
            "`intent-code index --full`.",
        )

    return (
        HASHING_SPEC,
        f"Ollama is running but the {model} model is not pulled; using the "
        "hashing embedder (lexical only). Run `intent-code index --full` to "
        f"fetch it automatically, or `ollama pull {model}` yourself.",
    )


def auto_embedder_spec(
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    allow_pull: bool = False,
) -> str:
    return describe_auto(model, host, allow_pull=allow_pull)[0]


class EmbedderUnavailable(RuntimeError):
    """The embedder this index was built with cannot be reached."""


@contextmanager
def embedder_guard(
    stored_spec: str, detected_spec: str | None = None
) -> Iterator[None]:
    """Turn a transport failure from the embedding backend into a remedy.

    An index built against Ollama keeps using Ollama, so stopping the server
    makes every query fail. Unguarded, that surfaces as a bare URLError raised
    deep inside urllib, which tells the caller nothing about what to do; the
    index is not corrupt and one command fixes it.
    """
    try:
        yield
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        if detected_spec and embedder_identity(detected_spec) != embedder_identity(
            stored_spec
        ):
            fix = f"run `intent-code index --full` to rebuild with {detected_spec}"
        else:
            fix = (
                "start the embedding server, or run `intent-code index --full` to "
                "rebuild with whatever is available"
            )
        raise EmbedderUnavailable(
            f"cannot reach the embedder this index was built with "
            f"({stored_spec}): {e}. To fix: {fix}."
        ) from e


def embedder_identity(spec: str) -> tuple:
    """Reduce a spec to a key that survives round-tripping through the store.

    intent-db persists the fully expanded spec (`hashing:dim=512,char_ngrams=1`,
    `ollama:model=x,host=y,dim=768,prefix_mode=nomic`) while detection returns
    the short form (`hashing:dim=512`, `ollama:model=x`). Comparing the raw
    strings would therefore report a mismatch every single time. Defaults are
    filled in here to match intent-db's `get_embedder`, and `dim` is excluded
    for Ollama because it is a property of the model, not a choice.
    """
    name, _, arg_str = spec.partition(":")
    name = name.strip().lower()
    args: dict[str, str] = {}
    for part in arg_str.split(","):
        key, sep, value = part.partition("=")
        if sep:
            args[key.strip()] = value.strip()

    if name == "hashing":
        return (name, args.get("dim", "512"), args.get("char_ngrams", "1"))
    if name == "ollama":
        return (
            name,
            args.get("model", DEFAULT_OLLAMA_MODEL),
            args.get("host", DEFAULT_OLLAMA_HOST).rstrip("/"),
            args.get("prefix_mode", "nomic"),
        )
    if name == "sbert":
        return (name, args.get("model", "all-MiniLM-L6-v2"))
    return (name, tuple(sorted(args.items())))
