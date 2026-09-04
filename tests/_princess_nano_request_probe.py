"""One-shot diagnostic: mirrors the Princess OpenAI request, never calls Fal."""
import json
from pathlib import Path

from dotenv import dotenv_values
from openai import OpenAI

repo = Path(__file__).resolve().parent.parent
values = dotenv_values(repo.parent / "Variables.env")
api_key = values.get("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is missing from C:/Users/danie/GitHub/Projects/Variables.env")

persona = " ".join(
    line.strip()
    for line in (repo / "assets" / "princess" / "princess_prompt.default.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.lstrip().startswith("#")
)

fixture = {
    "news": {"available": True, "data": {"headlines": [
        {"title": "Markets rise after central-bank announcement", "source": "Example News"},
        {"title": "Local rail services resume after morning disruption", "source": "Example News"},
        {"title": "Scientists publish new coastal restoration findings", "source": "Example News"},
    ]}, "reason": None},
    "weather": {"available": True, "data": {
        "location": "London", "temperature_c": 14, "feels_like_c": 12,
        "condition": "light rain", "wind_mps": 5.0,
    }, "reason": None},
    "calendar": {"available": True, "data": {"events": [
        {"title": "Project review", "start": "2026-09-04T14:00:00+01:00"},
    ]}, "reason": None},
    "smarthome": {"available": True, "data": {"entities": [
        {"name": "Living Room Lamp", "state": "on", "unit": ""},
        {"name": "Kitchen Plug", "state": "on", "unit": ""},
        {"name": "Hallway Light", "state": "off", "unit": ""},
        {"name": "Indoor Temperature", "state": "21.5", "unit": "°C"},
    ]}, "reason": None},
}

examples = [
    # Known local intent: production sends only the matching category.
    ("news / direct", "What are today's news headlines?", {"news": fixture["news"]}),
    # Unknown locally: production sends all already-fetched categories to Nano.
    ("weather / implied", "Will I need an umbrella later?", fixture),
    ("smarthome / ambiguous", "Did I leave anything on?", fixture),
]

def make_system(context):
    system = persona + " Reply with exactly one natural short sentence, at most 12 words. No markdown."
    return system + (
        " Classify the user's request as exactly one of general, news, weather, calendar, or smarthome. "
        "Use live facts only for the matching category; if that category is unavailable, say so plainly and invent nothing. "
        "Return exactly two lines: INTENT: <category> then REPLY: <your reply>. "
        f"Current mirror data: {json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )
client = OpenAI(api_key=api_key)
for label, user_text, context in examples:
    system = make_system(context)
    request = {
        "model": "gpt-5-nano-2025-08-07",
        "max_output_tokens": 160,
        "reasoning": {"effort": "minimal"},
        "input": [{"role": "system", "content": system}, {"role": "user", "content": user_text}],
    }
    print(f"\n[{label}] SENT (key intentionally omitted):")
    print(json.dumps(request, ensure_ascii=False, indent=2))
    try:
        response = client.responses.create(**request)
        print("RECEIVED:")
        print(response.output_text)
    except Exception as exc:
        print("API ERROR:")
        print(type(exc).__name__ + ": " + str(exc))
