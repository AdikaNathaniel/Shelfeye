"""Chat assistant: answers questions about the shelf inventory with OpenAI.

The question is sent to OpenAI together with the *live* inventory (stuffed into the
system prompt) and a few read-only tools over the events history. The model only
ever sees data from the inventory, events, shelves and nodes collections — never
user accounts, sessions or password resets. The OpenAI key stays on the server;
the browser only ever sends the user's question over its logged-in session.
"""
import json
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import env  # noqa: F401  (loads server/.env before any setting is read)
from auth import current_user
from db import database

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4.1-mini")

router = APIRouter(prefix="/api/assistant")

MAX_QUESTION_CHARS = 1500
MAX_MESSAGES = 16          # how much prior conversation we accept from the client
MAX_TOOL_ROUNDS = 4        # how many times the model may call tools before answering
RATE_LIMIT = 20            # questions per user per minute
RATE_WINDOW = 60

_rate_lock = threading.Lock()
_recent: dict[str, list[float]] = defaultdict(list)


def _rate_limit(user_id: str):
    now = time.monotonic()
    with _rate_lock:
        hits = [t for t in _recent[user_id] if now - t < RATE_WINDOW]
        if len(hits) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="You're sending questions too quickly. Please wait a moment.")
        hits.append(now)
        _recent[user_id] = hits


def _now():
    return datetime.now(timezone.utc)


def _since(days: float) -> str:
    return (_now() - timedelta(days=max(0.0, days))).isoformat(timespec="seconds")


# ---- Reading the data (only ever the four shelf collections) ----

def _shelf_names(db) -> dict:
    """node_id -> human shelf name, for cameras that have been given one."""
    return {s["node_id"]: s["name"] for s in db.shelves.find({"node_id": {"$type": "string"}}, {"node_id": 1, "name": 1})}


def inventory_context(db) -> str:
    """The whole current inventory, small enough to put straight in the prompt."""
    names = _shelf_names(db)
    rows = list(db.inventory.find().sort([("node_id", 1), ("name", 1)]))
    if not rows:
        return "The inventory is currently empty — no products have been counted yet."
    lines = []
    for r in rows:
        shelf = names.get(r["node_id"], r["node_id"])
        lines.append(f"- {r['name']}: {r['count']} in stock (shelf: {shelf}, last counted {r.get('updated_at', '?')})")
    return "Current inventory, live from the shelf cameras:\n" + "\n".join(lines)


def tool_recent_activity(db, days: float = 1) -> list:
    names = _shelf_names(db)
    rows = db.events.find({"captured_at": {"$gte": _since(days)}}).sort("captured_at", -1).limit(200)
    return [
        {"product": r["name"], "shelf": names.get(r["node_id"], r["node_id"]),
         "change": r["delta"], "from": r["previous"], "to": r["current"], "at": r["captured_at"]}
        for r in rows
    ]


def tool_product_history(db, name: str, days: float = 30) -> list:
    names = _shelf_names(db)
    pattern = re.compile(f"^{re.escape(name.strip())}$", re.IGNORECASE)
    rows = db.events.find({"name": pattern, "captured_at": {"$gte": _since(days)}}).sort("captured_at", -1).limit(200)
    return [
        {"product": r["name"], "shelf": names.get(r["node_id"], r["node_id"]),
         "change": r["delta"], "from": r["previous"], "to": r["current"], "at": r["captured_at"]}
        for r in rows
    ]


def tool_top_movers(db, days: float = 7) -> list:
    rows = db.events.aggregate([
        {"$match": {"captured_at": {"$gte": _since(days)}}},
        {"$group": {
            "_id": "$name",
            "taken": {"$sum": {"$cond": [{"$lt": ["$delta", 0]}, {"$abs": "$delta"}, 0]}},
            "added": {"$sum": {"$cond": [{"$gt": ["$delta", 0]}, "$delta", 0]}},
        }},
        {"$sort": {"taken": -1}},
        {"$limit": 15},
    ])
    return [{"product": r["_id"], "taken": r["taken"], "added": r["added"]} for r in rows]


TOOLS_SPEC = [
    {"type": "function", "function": {
        "name": "recent_activity",
        "description": "Items taken or added recently across all shelves, newest first. Use for 'what changed today/this week'.",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "number", "description": "How many days back to look (default 1)."}}},
    }},
    {"type": "function", "function": {
        "name": "product_history",
        "description": "The take/add history of one product by exact name. Use for 'how has X been moving', 'when did X run out'.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Exact product name as it appears in the inventory."},
            "days": {"type": "number", "description": "How many days back to look (default 30)."}},
            "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "top_movers",
        "description": "The most taken (and added) products over a period. Use for 'what's selling most', 'busiest items'.",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "number", "description": "How many days back to look (default 7)."}}},
    }},
]

TOOL_FUNCS = {"recent_activity": tool_recent_activity, "product_history": tool_product_history, "top_movers": tool_top_movers}


def _run_tool(db, name: str, args: dict):
    func = TOOL_FUNCS.get(name)
    if not func:
        return {"error": f"unknown tool {name}"}
    try:
        return func(db, **args)
    except Exception as exc:  # a bad argument from the model shouldn't 500 the request
        return {"error": str(exc)}


def _system_prompt(db) -> str:
    today = _now().strftime("%A, %d %B %Y")
    return (
        "You are ShelfEye's inventory assistant for a pharmacy. You help staff with questions about the "
        "drugs and products on the shelves: how many are left, what is low or out of stock, and what has "
        "been taken or added over time.\n\n"
        f"Today is {today} (UTC).\n\n"
        "Answer only from the data below and the tools provided. The inventory list is live and authoritative "
        "for current stock — use it directly for 'how many' and 'what's low' questions; never invent a number. "
        "For questions about changes over time, call a tool. If a product isn't in the inventory, say it isn't "
        "being tracked rather than guessing. Keep answers short and practical; round times to 'today', 'yesterday', "
        "etc. where natural. You can only see inventory data — politely decline anything unrelated.\n\n"
        f"{inventory_context(db)}"
    )


# ---- The endpoint ----

class Message(BaseModel):
    role: str
    content: str


class ChatBody(BaseModel):
    messages: list[Message]


class ChatReply(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatReply)
def chat(body: ChatBody, user: dict = Depends(current_user)):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="The assistant isn't configured (OPENAI_API_KEY is missing on the server).")
    _rate_limit(user["id"])

    turns = [m for m in body.messages if m.role in ("user", "assistant") and m.content.strip()][-MAX_MESSAGES:]
    if not turns or turns[-1].role != "user":
        raise HTTPException(status_code=400, detail="Ask a question to get started.")
    if len(turns[-1].content) > MAX_QUESTION_CHARS:
        raise HTTPException(status_code=400, detail="That question is too long. Please shorten it.")

    try:
        from openai import OpenAI
    except ImportError:
        raise HTTPException(status_code=503, detail="The assistant isn't installed on the server (the 'openai' package is missing).")

    db = database()
    client = OpenAI(api_key=OPENAI_API_KEY)
    messages = [{"role": "system", "content": _system_prompt(db)}]
    messages += [{"role": m.role, "content": m.content} for m in turns]

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            completion = client.chat.completions.create(
                model=OPENAI_MODEL, messages=messages, tools=TOOLS_SPEC, temperature=0.2,
            )
            msg = completion.choices[0].message
            if not msg.tool_calls:
                return ChatReply(reply=(msg.content or "").strip() or "I'm not sure how to answer that.")
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except ValueError:
                    args = {}
                result = _run_tool(db, tc.function.name, args)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)})
        return ChatReply(reply="That took more steps than I can handle in one go — try asking it more simply.")
    except HTTPException:
        raise
    except Exception as exc:  # OpenAI/network error
        raise HTTPException(status_code=502, detail=f"The assistant couldn't reach OpenAI right now ({exc}).")
