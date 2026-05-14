import json
from typing import List, Dict

import httpx

from app.core.config import get_settings

settings = get_settings()


async def chat_complete(messages: List[Dict[str, str]]) -> str:
    """Provider-agnostic chat call. Returns assistant text or a graceful fallback."""
    provider = (settings.AI_PROVIDER or "ollama").lower()
    try:
        if provider == "openai":
            return await _openai_chat(messages)
        return await _ollama_chat(messages)
    except Exception as e:  # noqa: BLE001
        return _fallback_response(messages, str(e))


async def _ollama_chat(messages: List[Dict[str, str]]) -> str:
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        return data.get("message", {}).get("content", "").strip() or "(no response)"


async def _openai_chat(messages: List[Dict[str, str]]) -> str:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": settings.OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()


def _fallback_response(messages: List[Dict[str, str]], err: str) -> str:
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    return (
        "The AI assistant is currently unavailable, but here's what I can tell you from your records:\n\n"
        + _rule_based_answer(last_user, messages)
        + f"\n\n_(AI service note: {err})_"
    )


def _rule_based_answer(user_msg: str, messages: List[Dict[str, str]]) -> str:
    msg = user_msg.lower()
    # Pull last system payload (data context) if present
    ctx = ""
    for m in messages:
        if m["role"] == "system" and m["content"].startswith("CONTEXT_JSON:"):
            ctx = m["content"][len("CONTEXT_JSON:"):]
            break
    try:
        data = json.loads(ctx) if ctx else {}
    except json.JSONDecodeError:
        data = {}

    parts = []
    if "appointment" in msg:
        appts = data.get("appointments", [])
        if appts:
            parts.append("Your next appointments:")
            for a in appts[:5]:
                parts.append(f"- {a.get('scheduled_at')} with {a.get('doctor')} ({a.get('status')})")
        else:
            parts.append("You have no upcoming appointments.")
    if "prescription" in msg or "medicine" in msg:
        pres = data.get("prescriptions", [])
        if pres:
            parts.append("Recent prescriptions:")
            for p in pres[:3]:
                parts.append(f"- {p.get('created_at')}: {p.get('diagnosis') or 'no diagnosis'} ({p.get('items')} items)")
        else:
            parts.append("No prescriptions on file.")
    if "bill" in msg or "payment" in msg or "invoice" in msg:
        bills = data.get("bills", [])
        if bills:
            parts.append("Bills overview:")
            for b in bills[:5]:
                parts.append(f"- #{b['id']} total {b['total']:.2f} (paid {b['paid']:.2f}) — {b['status']}")
        else:
            parts.append("No bills on file.")
    if "report" in msg:
        reports = data.get("reports", [])
        if reports:
            parts.append("Medical reports:")
            for r in reports[:5]:
                parts.append(f"- {r['title']} ({r['created_at']})")
        else:
            parts.append("No medical reports on file.")
    if not parts:
        parts.append(
            "I can help with appointments, prescriptions, bills, reports, and navigation. "
            "Try asking: 'show my appointments' or 'do I have any unpaid bills?'"
        )
    return "\n".join(parts)
