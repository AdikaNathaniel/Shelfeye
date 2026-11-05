"""Send a shelf photo to the OpenAI API and get back product names and counts.

Uses the REST API through `requests` rather than the `openai` package, which
is hard to install on the Pi Zero's ARMv6 CPU.
"""
import base64
import json

import requests

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer"},
                    "label_text": {"type": "string"},
                },
                "required": ["name", "count", "label_text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def build_prompt(catalog):
    lines = [
        "You count stock on a shop shelf from a photo.",
        "For each distinct product, count the individual units you can see (boxes, bottles, packs).",
        "Read the product name from its label and copy the most legible label text into label_text.",
        "Only count units that are actually visible. Do not guess about rows hidden behind others.",
    ]
    if catalog:
        lines.append(
            "Products expected on this shelf. Use these exact names when a product matches, "
            "and include every one of them, with count 0 if none are visible:"
        )
        lines += [f"- {name}" for name in catalog]
        lines.append("If you see a product that is not in this list, add it using the name on its label.")
    return "\n".join(lines)


def analyze_image(jpeg_bytes, api_key, model, catalog, timeout=90):
    """Return a list of {"name", "count", "label_text"} for the products in the photo."""
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": build_prompt(catalog)},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Count the products on this shelf."},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                ],
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "shelf_count", "strict": True, "schema": SCHEMA},
        },
    }
    response = requests.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=body,
        timeout=timeout,
    )
    response.raise_for_status()
    message = response.json()["choices"][0]["message"]
    if message.get("refusal"):
        raise RuntimeError(f"Model refused: {message['refusal']}")

    # The model occasionally lists the same product twice; merge those.
    merged = {}
    for item in json.loads(message["content"])["items"]:
        name = item["name"].strip()
        count = max(0, int(item["count"]))
        if name in merged:
            merged[name]["count"] += count
        else:
            merged[name] = {"name": name, "count": count, "label_text": item["label_text"]}
    return list(merged.values())
