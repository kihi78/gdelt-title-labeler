"""Headline topic labelling with a local llama.cpp server (OpenAI-compatible API).

The prompt, topic definitions and decoding settings are the ones used in the preregistered study
(osf.io/znu3t, "Does GDELT's theme tagging cover the same news equally across languages?"). Keep them as they are:
a different prompt is a different measurement (change PROMPT_VERSION if you must).

    # start the server first (see README.md), then
    python label.py label    --in titles.csv --out labels.jsonl --tag qwen3.5-9b --parallel 4
    python label.py validate --in human_labels.csv --out validate.jsonl --tag qwen3.5-9b
    python label.py compare  a.jsonl b.jsonl           # agreement and kappa between two label files
    python label.py prompt-hash                          # fingerprint of the prompt template (compare across machines)

Input CSV (UTF-8, header row):  label: id (or gkg_record_id),topic,title   (topic: prices, fx, monetary, markets)
                                validate: no,topic,title,final   (final = human label 0/1; topic as in the study's CSV:
                                          prices/fx/monetary/markets or 物価/為替/金融政策・金利/株式市場)
Output: one JSON object per line {key, v, model, topic, title, ans, id?}. `key` is identical to the key used by the study
repository's cache (sha256 of "<tag>|<PROMPT_VERSION>|<topic>|<title>", no tag prefix for qwen2.5-7b), so files can be merged.
Answers are constrained to "1" or "0" by a grammar; temperature 0. Already answered questions are skipped (resume-safe).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

SERVER = "http://127.0.0.1:8089"
PROMPT_VERSION = "2026-10-17a"
TOPICS = {
    "prices": ("consumer prices and inflation",
               "consumer prices, inflation, the cost of living, or price increases or decreases of goods and services "
               "(including fuel, energy, food, rent, utility bills, fees and charges). NOT: asset prices (stocks, gold, "
               "crypto, house sale prices), one product's sale, discount or launch price."),
    "fx": ("exchange rates and currencies",
           "exchange rates, currency markets, the value of a currency, foreign-exchange reserves, or exchange-rate policy. "
           "NOT: counterfeit money, fraud, stock-index moves written in currency units (for example 'Nikkei 800 yen "
           "lower'), or metaphors."),
    "monetary": ("monetary policy and interest rates",
                 "a central bank's monetary policy or interest-rate decisions, outlooks or debates, including their effects "
                 "on loans or markets. NOT: a central bank's economic assessment or survey alone, bank supervision, tax "
                 "rates, or organisations that merely share an acronym."),
    "markets": ("stock markets",
                "stock markets or share prices: index moves, trading, or analysis and recommendations of stocks. NOT: a "
                "company's earnings or dividend announcement alone, or 'stocks' meaning inventories."),
}
TOPIC_JA = {"物価": "prices", "為替": "fx", "金融政策・金利": "monetary", "株式市場": "markets"}
GRAMMAR = 'root ::= "1" | "0"'
SYSTEM = "You judge news headlines in any language. Reply with a single digit: 1 or 0."
USER = ("Topic: {name}.\nCounts as the topic: {definition}\n"
        "Answer 1 if the article behind this headline is mainly about the topic or treats it "
        "in at least one paragraph; otherwise 0.\n\nHeadline: {title}")


def messages(topic: str, title: str) -> list[dict]:
    name, definition = TOPICS[topic]
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER.format(name=name, definition=definition, title=title)}]


def prompt_hash() -> str:
    """Fingerprint of everything that defines the question except the headline."""
    blob = json.dumps([PROMPT_VERSION, SYSTEM, USER, GRAMMAR, TOPICS], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def cache_key(tag: str, topic: str, title: str) -> str:
    prefix = "" if tag == "qwen2.5-7b" else f"{tag}|"
    return hashlib.sha256(f"{prefix}{PROMPT_VERSION}|{topic}|{title}".encode()).hexdigest()


def load_done(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {d["key"]: d["ans"] for d in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if d}


def ask(session: requests.Session, topic: str, title: str) -> str:
    for attempt in range(5):
        try:
            r = session.post(f"{SERVER}/v1/chat/completions", timeout=300,
                             json={"messages": messages(topic, title), "temperature": 0, "max_tokens": 2,
                                   "grammar": GRAMMAR, "cache_prompt": True})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()[:1]
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
    raise SystemExit("Cannot reach llama-server. Is it running on 127.0.0.1:8089?")


def run(items: list[dict], out: Path, tag: str, parallel: int) -> dict[str, str]:
    """items: dicts with topic, title (and optionally id). Appends answers to `out`; returns key -> answer."""
    done = load_done(out)
    todo = [it for it in items if cache_key(tag, it["topic"], it["title"]) not in done]
    print(f"{len(items)} questions, {len(items) - len(todo)} already answered, {len(todo)} to ask "
          f"(model tag {tag}, prompt {PROMPT_VERSION} / {prompt_hash()})", flush=True)
    lock, t0, n = threading.Lock(), time.perf_counter(), [0]
    local = threading.local()

    def work(it: dict) -> None:
        if not hasattr(local, "s"):
            local.s = requests.Session()
        ans = ask(local.s, it["topic"], it["title"])
        key = cache_key(tag, it["topic"], it["title"])
        rec = {"key": key, "v": PROMPT_VERSION, "model": tag, "topic": it["topic"], "title": it["title"], "ans": ans}
        if it.get("id"):
            rec["id"] = it["id"]
        with lock:
            done[key] = ans
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n[0] += 1
            if n[0] % 200 == 0:
                el = time.perf_counter() - t0
                print(f"  {n[0]}/{len(todo)}  {el:.0f}s  ({n[0] / el:.1f}/s)", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        list(pool.map(work, todo))
    return done


def read_csv(path: str) -> list[dict]:
    return list(csv.DictReader(open(path, encoding="utf-8-sig", newline="")))


def kappa(pairs: list[tuple[str, str]]) -> tuple[float, float, int]:
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a == "1" for a, _ in pairs) / n
    pb = sum(b == "1" for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return ((po - pe) / (1 - pe) if pe < 1 else math.nan), po, n


def cmd_label(a: argparse.Namespace) -> int:
    rows = read_csv(a.inp)
    items = [{"id": r.get("id") or r.get("gkg_record_id", ""), "topic": r["topic"], "title": r["title"]} for r in rows]
    bad = {i["topic"] for i in items} - set(TOPICS)
    if bad:
        raise SystemExit(f"unknown topic(s): {sorted(bad)}; use one of {sorted(TOPICS)}")
    run(items, Path(a.out), a.tag, a.parallel)
    return 0


def cmd_validate(a: argparse.Namespace) -> int:
    rows = [r for r in read_csv(a.inp) if r.get("final") in ("0", "1")]
    items = [{"id": r.get("no", ""), "topic": TOPIC_JA.get(r["topic"], r["topic"]), "title": r["title"]} for r in rows]
    done = run(items, Path(a.out), a.tag, a.parallel)
    pairs = [(r["final"], done[cache_key(a.tag, it["topic"], it["title"])]) for r, it in zip(rows, items)]
    k, po, n = kappa(pairs)
    tp = sum(h == "1" and m == "1" for h, m in pairs)
    tn = sum(h == "0" and m == "0" for h, m in pairs)
    pos = sum(h == "1" for h, _ in pairs)
    print(f"\nhuman vs {a.tag}: agreement {po:.0%}, kappa {k:.2f}, n={n}; "
          f"sensitivity {tp / pos:.0%}, specificity {tn / (n - pos):.0%}")
    return 0


def cmd_compare(a: argparse.Namespace) -> int:
    x, y = load_done(Path(a.a)), load_done(Path(a.b))
    both = sorted(set(x) & set(y))
    if not both:
        print("no common keys (different model tags change the key; use --retag)")
        return 1
    k, po, n = kappa([(x[i], y[i]) for i in both])
    print(f"common {n}: agreement {po:.0%}, kappa {k:.2f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("label", "validate"):
        s = sub.add_parser(name)
        s.add_argument("--in", dest="inp", required=True)
        s.add_argument("--out", required=True)
        s.add_argument("--tag", required=True, help="model name recorded in the keys, e.g. qwen3.5-9b")
        s.add_argument("--parallel", type=int, default=4, help="concurrent requests (match llama-server -np)")
    s = sub.add_parser("compare")
    s.add_argument("a")
    s.add_argument("b")
    sub.add_parser("prompt-hash")
    a = p.parse_args(argv)
    if a.cmd == "prompt-hash":
        print(f"{PROMPT_VERSION} {prompt_hash()}")
        return 0
    return {"label": cmd_label, "validate": cmd_validate, "compare": cmd_compare}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
