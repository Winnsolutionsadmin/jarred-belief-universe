#!/usr/bin/env python3
"""Build the Jarred belief UNIVERSE map (index.html) from canonical data.

Inputs (canonical, never hand-edited here):
  - belief-cluster-data.json  (jarred-belief-field nightly export from Notion)
  - thinkers.json             (belief-system-map generator corpus)

Output: index.html, rendered from template.html with three injected JS blobs:
  const data      = Jarred's 71-belief cluster (same database as the connection map)
  const thinkers  = the thinker profile corpus
  const universes = SEEDED per-thinker universes: stance nodes parsed from each
                    thinker's documented public positions, plus bridge nodes for
                    every Jarred belief they share. No researched content, no
                    invented quotes; provenance is the thinkers corpus only.

Every thinker referenced by any belief (allies/adversaries/related) gets a
universe entry, even when absent from thinkers.json (bridges only, no positions).

Usage:
  python3 generator/build-universe.py \
      [--cluster-data PATH] [--thinkers PATH] [--out PATH]
Idempotent: unchanged inputs produce an unchanged index.html (build date changes
only when content changes).
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEF_CLUSTER = Path.home() / "Projects/jarred-belief-field/data/belief-cluster-data.json"
DEF_THINKERS = Path.home() / "Projects/belief-system-map/generator/thinkers.json"
TEMPLATE = ROOT / "template.html"

DATA_LINE = re.compile(r"^const data = .*;$", re.MULTILINE)
THINKERS_LINE = re.compile(r"^const thinkers = .*;$", re.MULTILINE)
UNIVERSES_LINE = re.compile(r"^const universes = .*;$", re.MULTILINE)
DATE_TOKEN = "__BUILD_DATE__"

# "Label (meta): claim. Next Label: claim." segment splitter
SEG_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9][^.:]{0,80}:\s)")
LABELED = re.compile(r"^([^:]{2,90}):\s*(.+)$", re.DOTALL)


def js_blob(obj):
    blob = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")
    blob = blob.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return blob


def norm_title(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def slug_title_from_url(url):
    """'.../Computational-Ontology-Thesis-31fe...c6' -> 'computational ontology thesis'"""
    tail = url.rstrip("/").split("/")[-1]
    parts = tail.split("-")
    if parts and len(parts[-1]) == 32:
        parts = parts[:-1]
    return norm_title(" ".join(parts))


def parse_positions(text):
    """Split a positions summary into stance nodes [{label, claim}]. Seeded data
    is truncated prose; drop fragments without substance."""
    text = (text or "").strip()
    if not text:
        return []
    out = []
    for seg in SEG_SPLIT.split(text):
        seg = seg.strip()
        if not seg:
            continue
        m = LABELED.match(seg)
        if m and len(m.group(2).strip()) >= 12:
            out.append({"label": m.group(1).strip(), "claim": m.group(2).strip()})
        elif not m and len(seg) >= 25:
            out.append({"label": "Position", "claim": seg})
    if not out and len(text) >= 25:
        out = [{"label": "Position", "claim": text}]
    return out[:6]


def build_universes(beliefs, thinkers):
    """Seed per-thinker universes from the cluster beliefs + thinkers corpus.
    Shared by the 2D map (this script) and the 3D demo (jarred-belief-universe-3d).
    Returns (universes, matched_shared, unmatched_shared)."""
    # belief lookup by normalized title AND by Notion url slug (titles drift)
    by_key = {}
    for bid, b in beliefs.items():
        by_key[norm_title(b["title"])] = bid
        if b.get("url"):
            by_key.setdefault(slug_title_from_url(b["url"]), bid)

    # reverse index: thinker -> [(belief id, role)]
    referenced = {}
    for bid, b in beliefs.items():
        for role, field in (("ally", "allies"), ("adversary", "adversaries"), ("related", "related")):
            for name in b.get(field, []) or []:
                referenced.setdefault(name, []).append((bid, role))

    universes = {}
    names = sorted(set(thinkers) | set(referenced))
    matched_shared = unmatched_shared = 0
    for name in names:
        t = thinkers.get(name, {})
        shared, seen = [], set()
        # from the thinkers corpus: "Title [Cluster]" strings, resolve to belief ids
        for s in t.get("shared", []) or []:
            m = re.match(r"^(.*?)\s*\[([^\]]+)\]\s*$", s)
            title, cl = (m.group(1), m.group(2)) if m else (s, "")
            bid = by_key.get(norm_title(title))
            key = bid or norm_title(title)
            if key in seen:
                continue
            seen.add(key)
            if bid:
                matched_shared += 1
                shared.append({"belief": int(bid), "title": beliefs[bid]["title"], "role": "shared"})
            else:
                unmatched_shared += 1
                shared.append({"belief": None, "title": title, "role": "shared"})
        # from the belief field itself: every belief that names this thinker
        for bid, role in referenced.get(name, []):
            if bid in seen:
                continue
            seen.add(bid)
            shared.append({"belief": int(bid), "title": beliefs[bid]["title"], "role": role})
        universes[name] = {
            "alignment": t.get("alignment", ""),
            "url": t.get("url", ""),
            "positions": parse_positions(t.get("positions", "")),
            "shared": shared,
            "diverges": (t.get("diverges") or "").strip(),
            "bridge": (t.get("bridge") or "").strip(),
            "notes": t.get("quotes", []) or [],
            "seeded": True,
        }
    return universes, matched_shared, unmatched_shared


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cluster-data", default=str(DEF_CLUSTER))
    ap.add_argument("--thinkers", default=str(DEF_THINKERS))
    ap.add_argument("--out", default=str(ROOT / "index.html"))
    args = ap.parse_args()

    cluster = json.loads(Path(args.cluster_data).read_text(encoding="utf-8"))
    beliefs = cluster["beliefs"]
    thinkers = json.loads(Path(args.thinkers).read_text(encoding="utf-8"))
    universes, matched_shared, unmatched_shared = build_universes(beliefs, thinkers)

    html = TEMPLATE.read_text(encoding="utf-8")
    for rx, label, blob in (
        (DATA_LINE, "data", beliefs),
        (THINKERS_LINE, "thinkers", thinkers),
        (UNIVERSES_LINE, "universes", universes),
    ):
        if len(rx.findall(html)) != 1:
            sys.exit(f"ERROR: expected exactly one 'const {label} = ...;' line in template")
        html = rx.sub(lambda _m, l=label, b=blob: f"const {l} = " + js_blob(b) + ";", html, count=1)

    out = Path(args.out)
    prev = out.read_text(encoding="utf-8") if out.exists() else ""
    # idempotence: only stamp a new date when content (minus the date) changed
    prev_undated = re.sub(r"Last updated: \d{4}-\d{2}-\d{2}", f"Last updated: {DATE_TOKEN}", prev)
    if prev_undated == html:
        print(f"[universe] {out.name} already current "
              f"({len(beliefs)} beliefs, {len(universes)} universes)")
        return
    html = html.replace(DATE_TOKEN, date.today().isoformat())
    out.write_text(html, encoding="utf-8")
    npos = sum(1 for u in universes.values() if u["positions"])
    print(f"[universe] wrote {out}: {len(beliefs)} beliefs, {len(universes)} universes "
          f"({npos} with seeded positions), shared resolved={matched_shared} unresolved={unmatched_shared}")


if __name__ == "__main__":
    main()
