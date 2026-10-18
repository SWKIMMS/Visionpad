"""Prepare source-backed demo speech through a running server, without game actions."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import tempfile
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game_speech import spoken_text
from tools.audio_flow import run_flow
from tools.speech_inventory import collect


def demo_lines():
    """Use exact fixed lines, NPC branches and a temporary engine's real responses."""
    lines = {}

    def add(text, profile, origin):
        if not text or not str(text).strip():
            return
        key = (profile, spoken_text(text))
        entry = lines.setdefault(key, {"text": str(text).strip(), "profile": profile, "sources": []})
        if origin not in entry["sources"]:
            entry["sources"].append(origin)

    for entry in collect():
        if entry["kind"] == "fixed":
            add(entry["text"], "system", f'{entry["source"]}:{entry["line"]}')

    config = json.loads((ROOT / "speech_config.json").read_text())
    for sample in config["samples"]:
        add(sample["text"], "system", "speech_config.json:" + sample["id"])

    npcs = json.loads((ROOT / "npc_config.json").read_text())
    for npc_id, npc in npcs.items():
        topics = {key: npc[key] for key in ("greeting", "return_greeting", "goodbye")}
        topics.update({f"farming.{key}": text for key, text in npc["farming"].items()})
        topics.update({f"fishing.{key}": text for key, text in npc["fishing"].items()})
        for topic, text in topics.items():
            add(f'{npc["name"]}. {text}', npc["voice_profile"], f"npc_config.json:{npc_id}.{topic}")

    # Exercise the team's tutorial in temporary progress, so gifts/rewards only
    # shape the sample lines and never touch a running player's game.
    from game_engine import GameEngine
    with tempfile.TemporaryDirectory(prefix="visionpad-demo-quest-") as saved:
        engine = GameEngine(json.loads((ROOT / "game_config.json").read_text()), save_dir=saved)
        engine.travel_to("town")

        def quest_line(result):
            add(result.get("tts"), result.get("speech_profile", "system"), "demo:quest")

        quest_line(engine.talk_rowan())
        quest_line(engine.talk_rowan())
        engine.open_inventory()
        engine.use_food("rowan_soup")
        engine.travel_to("town")
        quest_line(engine.talk_rowan())
        quest_line(engine.talk_rowan())
        quest_line(engine.talk_rowan())
        engine.resources["crops"]["tomato"] = 1
        quest_line(engine.talk_rowan())
        quest_line(engine.submit_rowan_crop("tomato"))
        quest_line(engine.talk_rowan())
        for day in range(1, 8):
            engine.day = day
            quest_line(engine.open_calendar())

    # Only literal test-button calls are read; JavaScript is never evaluated.
    page = (ROOT / "web/game.html").read_text()
    for match in re.finditer(r'\b(?:announce|speak)\(("(?:\\.|[^"\\])*")([^;\n]*)', page):
        profile = "shopkeeper" if '"shopkeeper"' in match[2] else "system"
        add(json.loads(match[1]), profile, "web/game.html:test-button")

    flow = run_flow()
    for event in flow["events"]:
        response = event["response"]
        add(response.get("tts"), response.get("speech_profile", "system"), "demo:action")
        for sound in response.get("sound_events", []):
            add(sound.get("tts"), "system", "demo:sound-event")
        for obj in response["state"].get("objects", []):
            # Save labels contain the wall-clock date and cannot be reused in a demo.
            if obj.get("type") != "save_slot":
                add(obj.get("description"), "system", "demo:object")
    return list(lines.values())


class ServerSpeech:
    def __init__(self, server):
        self.server = server.rstrip("/")

    def request(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = Request(self.server + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                detail = json.load(error).get("detail", str(error))
            except (ValueError, OSError):
                detail = str(error)
            raise RuntimeError(detail) from error

    def catalogue(self):
        return self.request("/api/speech/voices")

    def generate(self, text, profile, rate):
        return self.request("/api/speech", {"text": text, "profile": profile, "rate": rate, "priority": "background"})


def prepare(lines, service, rate=1.0, progress=None):
    ready = {profile["id"] for profile in service.catalogue()["profiles"] if profile["ready"]}
    missing = {line["profile"] for line in lines} - ready
    if missing:
        raise RuntimeError("Voice setup needed: " + ", ".join(sorted(missing)))
    results, failures = [], []
    started = perf_counter()
    for index, line in enumerate(lines, 1):
        at = perf_counter()
        try:
            result = service.generate(line["text"], line["profile"], rate)
            results.append({**line, **result, "rate": rate, "request_ms": round((perf_counter()-at)*1000, 2)})
        except (OSError, ValueError, RuntimeError) as error:
            failures.append({**line, "error": str(error)})
        if progress:
            progress(index, len(lines))
    return {"rate": rate, "total": len(lines), "ready": len(results),
            "cache_hits": sum(bool(result["cache_hit"]) for result in results),
            "generated": sum(not result["cache_hit"] for result in results),
            "elapsed_seconds": round(perf_counter()-started, 2),
            "complete": not failures, "failures": failures, "lines": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="Running game server")
    parser.add_argument("--rate", type=float, default=1.0, help="Prepare this playback rate (0.8 to 1.5)")
    parser.add_argument("--list", action="store_true", help="List source-backed lines without generating speech")
    parser.add_argument("--report", type=Path, default=ROOT / "output/audio/demo-ready.json")
    args = parser.parse_args()
    if not 0.8 <= args.rate <= 1.5:
        parser.error("rate must be between 0.8 and 1.5")
    lines = demo_lines()
    if args.list:
        print(json.dumps({"total": len(lines), "profiles": dict(Counter(line["profile"] for line in lines)),
                          "lines": lines}, indent=2))
        return

    def progress(index, total):
        if index % 10 == 0 or index == total:
            print(f"Preparing demo voices: {index}/{total}", flush=True)

    try:
        report = prepare(lines, ServerSpeech(args.server), args.rate, progress)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not prepare demo voices: {error}\nStart the game server and check voice setup.\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Ready {report['ready']}/{report['total']}; generated {report['generated']}; "
          f"reused {report['cache_hits']}; {report['elapsed_seconds']} seconds. Report: {args.report}")
    if not report["complete"]:
        parser.exit(1, "Some voices could not be prepared. Retry to reuse completed clips.\n")


if __name__ == "__main__":
    main()
