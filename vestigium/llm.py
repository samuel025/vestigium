"""Gemini wrapper. Set GEMINI_API_KEY (or GOOGLE_API_KEY) and optionally VESTIGIUM_MODEL."""
import os, json, re, time, functools
from google import genai
from google.genai import types

def _load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            k, _, v = line.strip().partition("=")
            if k and not k.startswith("#") and v and k not in os.environ:
                os.environ[k] = v


_load_env()
MODEL = os.environ.get("VESTIGIUM_MODEL", "gemini-2.5-flash")
class DailyQuotaExhausted(RuntimeError):
    pass


_clients, _next_ok = [], []   # per-key earliest next-call time
RPM = float(os.environ.get("VESTIGIUM_RPM", "6"))  # per key


def _init():
    global _clients, _next_ok
    if not _clients:
        keys = [os.environ[k] for k in sorted(os.environ) if k.startswith("GEMINI_API_KEY") and os.environ[k]]
        if not keys:
            raise RuntimeError("No GEMINI_API_KEY set in .env")
        _clients = [genai.Client(api_key=k, http_options=types.HttpOptions(api_version="v1beta", timeout=60_000)) for k in keys]
        _next_ok = [0.0] * len(keys)


def pick():
    """Return (index, client) of the key that is free soonest; sleep until it is. Keys are independent projects."""
    _init()
    i = min(range(len(_clients)), key=lambda j: _next_ok[j])
    wait = _next_ok[i] - time.time()
    if wait > 1800:
        raise DailyQuotaExhausted("all Gemini keys are out of daily quota; rerun after the reset (midnight Pacific)")
    if wait > 0:
        time.sleep(wait)
    _next_ok[i] = time.time() + 60.0 / RPM
    return i, _clients[i]


def cooldown(i, secs):
    _next_ok[i] = max(_next_ok[i], time.time() + secs)


def _generate(contents, cfg):
    """One paced Gemini call; rotates keys and cools down on 429/503."""
    for attempt in range(10):
        i, c = pick()
        try:
            return c.models.generate_content(model=MODEL, contents=contents, config=cfg)
        except Exception as e:
            msg = str(e)
            if isinstance(e, DailyQuotaExhausted) or attempt == 9 or not any(x in msg for x in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "timed out", "Timeout", "disconnected", "ReadError", "ConnectError")):
                raise
            if "PerDay" in msg or "per_day" in msg or "limit: 500" in msg or "RequestsPerDay" in msg:
                cooldown(i, 6 * 3600)          # daily quota: park this key until the reset
            else:
                cooldown(i, 60 if "429" in msg or "RESOURCE_EXHAUSTED" in msg else 10)


def ask(system, prompt, tools=(), max_calls=12):
    """Agent turn with a hand-written tool loop: every model call is paced, retries resume the run,
    and tool calls are hard-capped at max_calls. Returns (parsed_json|None, stats)."""
    fns = {t.__name__: t for t in tools}
    st = dict(tool_calls=0, tool_errors=0, tokens=0, model_calls=0, error_log=[], trace=[])
    cfg = types.GenerateContentConfig(
        system_instruction=system, temperature=0.2, tools=list(tools) or None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    text = ""
    for _ in range(max_calls + 2):
        if st["tool_calls"] >= max_calls and tools:   # budget spent: force a final answer
            contents.append(types.Content(role="user", parts=[types.Part(text="Tool budget used up. Give your final JSON answer now.")]))
            cfg.tools = None
        r = _generate(contents, cfg)
        st["model_calls"] += 1
        if r.usage_metadata:
            st["tokens"] += r.usage_metadata.total_token_count or 0
        calls = r.function_calls or []
        if not calls:
            text = r.text or ""
            break
        contents.append(r.candidates[0].content)
        parts = []
        said = " ".join(p.text for p in (r.candidates[0].content.parts or []) if getattr(p, "text", None))
        for fc in calls:
            st["tool_calls"] += 1
            try:
                out = fns[fc.name](**(fc.args or {}))
                out = out if isinstance(out, dict) else {"result": out}
            except Exception as e:
                st["tool_errors"] += 1
                st["error_log"].append(f"{fc.name}: {str(e)[:120]}")
                out = {"error": str(e)[:300]}
            st["trace"].append(dict(step=len(st["trace"]) + 1, said=said[:400] if said else None, tool=fc.name, args=dict(fc.args or {}),
                                    result=json.dumps(out, default=str)[:1800]))
            said = ""   # only attach the model's words to the first call of a turn
            parts.append(types.Part.from_function_response(name=fc.name, response=out))
        contents.append(types.Content(role="user", parts=parts))
    st["error_log"] = st["error_log"][:3]
    st["final_text"] = (text or "")[:1500]
    ans = _parse(text)
    if ans is None:  # one repair retry: same conversation, ask for the JSON object only
        st["raw_unparsed"] = text[:500]
        st["parse_retry"] = True
        try:
            contents.append(types.Content(role="model", parts=[types.Part(text=text or "(empty)")]))
            contents.append(types.Content(role="user", parts=[types.Part(text="Your last reply was not a valid JSON object. Reply with ONLY the JSON object requested, nothing else.")]))
            cfg.tools = None
            r = _generate(contents, cfg)
            st["model_calls"] += 1
            st["tokens"] += (r.usage_metadata.total_token_count or 0) if r.usage_metadata else 0
            ans = _parse(r.text or "")
        except DailyQuotaExhausted:
            raise
        except Exception as e:
            st["error_log"].append(f"repair: {str(e)[:100]}")
    return ans, st


def _parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None
