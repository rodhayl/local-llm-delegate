"""Fleet review — fan out a swarm of strong-model agents over a whole codebase.

The fleet COMMANDER (this script, run locally) sends as many strong-model worker
agents as needed to review every reviewable file, then routes their merged findings
to ONE strong AUDITOR agent for a full second-pass review before returning a single
tight report. Stdlib-only; it shells out to the sibling ``llm_strong.py`` wrapper.

Three tiers, by confidentiality (the routing the operator asked for):
  * HARD-DENIED files (``.env``, ``*secret*``, keys, ``live_config_snapshot_*`` …,
    via ``llm_strong.denied_pattern``) are NEVER uploaded — listed as "not reviewed
    (sensitive)" so a human handles them.
  * CONFIDENTIAL files (match a confidential glob) -> PAID strong agents with privacy
    ON (``OPENCODE_MODEL``): content is redacted on upload, proprietary code stays put.
  * everything else -> FREE strong agents (``llm_strong.py --no-privacy`` ->
    ``OPENCODE_MODEL_OPEN``): cheap second-Sonnet-class review of non-secret source.

Workers use the bundled ``review`` runbook (false-positive-resistant, confidence-tagged).
The auditor runs PAID privacy-ON (it sees findings that may quote confidential code),
dedupes across workers, drops the false positives a single worker can't see are dups,
ranks by severity, and emits ONE compact table — that is all that comes back to you.

Usage:
    # plan only (no agents spawned, no cost) — see the partition + routing
    python fleet_review.py --scope "src/**" --dry-run
    # real run over a module, free + paid workers + audit
    python fleet_review.py --scope "src/**" \
        --confidential-glob "config/**" --max-words 350
    # whole tracked codebase
    python fleet_review.py

Efficiency knobs: --files-per-worker / --kb-per-worker size each agent's slice;
--max-workers caps fan-out; --concurrency caps parallel API calls (429-friendly);
workers + auditor run --caveman with a word budget so the report stays terse.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import fnmatch
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LLM_STRONG = HERE / "llm_strong.py"
sys.path.insert(0, str(HERE))
import llm_strong  # noqa: E402  (reuse its deny-list / redaction routing)

# Files worth sending to a code reviewer. Everything else (binaries, lockfiles,
# generated artifacts, vendored trees) is skipped before any agent is spawned.
SOURCE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".sh", ".bash",
    ".ps1", ".sql", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
}
SKIP_PARTS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".worktrees", "generated", ".qoder", "vendor", "site-packages",
}
SKIP_NAME_RE = re.compile(r"(\.min\.|\.lock$|package-lock\.json$|\.map$|\.pyc$)")
DEFAULT_KB_PER_WORKER = 110          # under the 240KB inline cap, leaves prompt room
DEFAULT_FILES_PER_WORKER = 12
DEFAULT_CONCURRENCY = 2             # parallel API calls
MAX_CONCURRENCY = 2                 # hard cap: higher fan-out triggers backend errors


def sh(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def repo_root() -> Path:
    top = sh(["git", "rev-parse", "--show-toplevel"]).strip()
    return Path(top) if top else Path.cwd()


def tracked_files(root: Path) -> list[str]:
    out = sh(["git", "-C", str(root), "ls-files"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def reviewable(rel: str, exts: set[str]) -> bool:
    p = Path(rel)
    if any(part in SKIP_PARTS for part in p.parts):
        return False
    if SKIP_NAME_RE.search(p.name):
        return False
    return p.suffix.lower() in exts


def match_any(rel: str, globs: list[str]) -> bool:
    # match against the full posix path and the bare name, both directions
    posix = Path(rel).as_posix()
    return any(fnmatch.fnmatch(posix, g) or fnmatch.fnmatch(Path(rel).name, g)
               for g in globs)


def classify(root: Path, files: list[str], confidential_globs: list[str]) -> dict:
    """Split into skip (hard-denied) / confidential (paid) / open (free)."""
    skip, confidential, open_ = [], [], []
    for rel in files:
        abs = str(root / rel)
        if llm_strong.denied_pattern(abs):           # secret/key/.env → never upload
            skip.append(rel)
        elif match_any(rel, confidential_globs):
            confidential.append(rel)
        else:
            open_.append(rel)
    return {"skip": skip, "confidential": confidential, "open": open_}


def partition(root: Path, files: list[str], kb: int, max_files: int) -> list[list[str]]:
    """Greedy pack into chunks within a byte budget and a file-count cap."""
    budget = kb * 1024
    chunks: list[list[str]] = []
    cur: list[str] = []
    cur_bytes = 0
    for rel in sorted(files):
        try:
            size = (root / rel).stat().st_size
        except OSError:
            size = 0
        if cur and (cur_bytes + size > budget or len(cur) >= max_files):
            chunks.append(cur)
            cur, cur_bytes = [], 0
        cur.append(rel)
        cur_bytes += size
    if cur:
        chunks.append(cur)
    return chunks


def cap_workers(chunks: list[list[str]], max_workers: int) -> list[list[str]]:
    """If over the worker budget, merge the smallest tail chunks together."""
    if max_workers <= 0 or len(chunks) <= max_workers:
        return chunks
    head = chunks[: max_workers - 1]
    tail: list[str] = [f for c in chunks[max_workers - 1:] for f in c]
    return head + [tail]


# ── usage telemetry parsing (from the wrappers' stderr) ──────────────────────
_USAGE_RE = re.compile(r"prompt=(\d+) completion=(\d+)")


def sum_tokens(stderr: str) -> tuple[int, int]:
    p = c = 0
    for m in _USAGE_RE.finditer(stderr or ""):
        p += int(m.group(1))
        c += int(m.group(2))
    return p, c


def run_worker(root: Path, files: list[str], paid: bool, max_words: int,
               timeout: int, worker_runbook: str = "review") -> dict:
    """One strong-agent review over a slice of files. Returns its findings."""
    KNOWN_RUNBOOKS = {"review", "improve", "triage", "summarize", "count",
                      "commit", "supervise", "watch", "fleet"}
    if worker_runbook not in KNOWN_RUNBOOKS and not worker_runbook.endswith(".md"):
        raise ValueError(f"unknown runbook: {worker_runbook}")
    cmd = [sys.executable, str(LLM_STRONG), "--runbook", worker_runbook,
           "--caveman", "--max-words", str(max_words), "--timeout", str(timeout)]
    if not paid:
        cmd.append("--no-privacy")            # → free OPENCODE_MODEL_OPEN tier
    for rel in files:
        cmd += ["-f", str(root / rel)]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 60)
    except subprocess.TimeoutExpired:
        return {
            "files": files, "paid": paid, "ok": False, "findings": "",
            "err": f"worker timed out after {timeout + 60}s",
            "secs": round(time.time() - t0, 1), "ptok": 0, "ctok": 0,
        }
    except OSError as exc:
        return {
            "files": files, "paid": paid, "ok": False, "findings": "",
            "err": f"worker failed to start: {exc}",
            "secs": round(time.time() - t0, 1), "ptok": 0, "ctok": 0,
        }
    pt, ct = sum_tokens(proc.stderr)
    return {
        "files": files, "paid": paid, "ok": proc.returncode == 0,
        "findings": (proc.stdout or "").strip(),
        "err": (proc.stderr or "").strip()[-400:],
        "secs": round(time.time() - t0, 1), "ptok": pt, "ctok": ct,
    }


AUDIT_PROMPT = """You are the FLEET AUDITOR: a senior reviewer doing the FINAL pass over findings
produced by many independent worker agents that each saw only a slice of the codebase.
The raw, per-worker findings (each block headed by its file slice + tier) are in the input.

Do a full review of those findings and return ONE consolidated report:
- DEDUPE: collapse the same defect reported by multiple workers into a single row.
- DROP false positives and anything a worker marked LOW confidence that you cannot
  corroborate from its own evidence — workers over-flag; you are the gate.
- KEEP cross-file issues: if two workers' findings combine into a real defect, say so.
- RANK by severity (HIGH first), then by confidence.
- Be terse. No praise, no restating what code does.

OUTPUT exactly:
1. One line: `FLEET VERDICT: SHIP | FIX-FIRST | NEEDS-DISCUSSION` + trade-blocking? yes/no.
2. A table, highest severity first, one row per real issue:
   SEV(H|M|L) | CONF(H|M|L) | file:symbol | defect (<=15 words) | fix (<=12 words)
3. If nothing real survives: `No actionable defects after audit.`
Cap the whole answer at the word budget. Findings only."""


IMPROVE_AUDIT_NOTE = """
LENS OVERRIDE: these are STRUCTURE/QUALITY improvements, not correctness defects.
Read "defect" as "weakness", and use this verdict line instead:
`FLEET VERDICT: SOLID | POLISH | RESTRUCTURE`. Table columns become:
IMPACT(H|M|L) | CONF(H|M|L) | file:symbol | weakness (<=15 words) | improvement (<=12 words)."""


def run_auditor(merged: str, root: Path, max_words: int, timeout: int,
                no_privacy: bool, lens: str = "review") -> dict:
    tmp = root / ".llm_delegate" / "fleet_findings_raw.md"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(merged, encoding="utf-8")
    prompt = AUDIT_PROMPT + (IMPROVE_AUDIT_NOTE if lens == "improve" else "")
    cmd = [sys.executable, str(LLM_STRONG), prompt, "-f", str(tmp),
           "--caveman", "--max-words", str(max_words), "--timeout", str(timeout)]
    if no_privacy:
        cmd.append("--no-privacy")
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 60)
    except subprocess.TimeoutExpired:
        return {
            "ok": False, "report": "", "err": f"auditor timed out after {timeout + 60}s",
            "raw_path": str(tmp), "secs": round(time.time() - t0, 1), "ptok": 0, "ctok": 0,
        }
    except OSError as exc:
        return {
            "ok": False, "report": "", "err": f"auditor failed to start: {exc}",
            "raw_path": str(tmp), "secs": round(time.time() - t0, 1), "ptok": 0, "ctok": 0,
        }
    pt, ct = sum_tokens(proc.stderr)
    return {
        "ok": proc.returncode == 0, "report": (proc.stdout or "").strip(),
        "err": (proc.stderr or "").strip()[-400:], "raw_path": str(tmp),
        "secs": round(time.time() - t0, 1), "ptok": pt, "ctok": ct,
    }


def build_plan(root: Path, args) -> dict:
    exts = set(SOURCE_EXTS) | {e if e.startswith(".") else "." + e
                               for e in (args.include_ext or [])}
    if args.paths:
        files = [p for p in args.paths if reviewable(p, exts)]
    else:
        pool = tracked_files(root)
        if args.scope:
            pool = [f for f in pool if match_any(f, args.scope)]
        files = [f for f in pool if reviewable(f, exts)]
    conf_globs = list(args.confidential_glob)
    env_globs = os.environ.get("LLM_FLEET_CONFIDENTIAL_GLOBS", "")
    conf_globs += [g.strip() for g in env_globs.split(",") if g.strip()]
    buckets = classify(root, files, conf_globs)
    conf_chunks = cap_workers(
        partition(root, buckets["confidential"], args.kb_per_worker, args.files_per_worker),
        args.max_workers)
    open_chunks = cap_workers(
        partition(root, buckets["open"], args.kb_per_worker, args.files_per_worker),
        args.max_workers)
    return {"buckets": buckets, "conf_chunks": conf_chunks,
            "open_chunks": open_chunks, "conf_globs": conf_globs, "n_files": len(files)}


def print_plan(plan: dict) -> None:
    b = plan["buckets"]
    print("FLEET PLAN", file=sys.stderr)
    print(f"  reviewable files: {plan['n_files']}", file=sys.stderr)
    print(f"  confidential (PAID privacy-ON): {len(b['confidential'])} files "
          f"-> {len(plan['conf_chunks'])} worker(s)", file=sys.stderr)
    print(f"  open (FREE --no-privacy): {len(b['open'])} files "
          f"-> {len(plan['open_chunks'])} worker(s)", file=sys.stderr)
    print(f"  skipped (sensitive, NOT uploaded): {len(b['skip'])}", file=sys.stderr)
    if b["skip"]:
        print("    " + ", ".join(b["skip"][:10])
              + (" …" if len(b["skip"]) > 10 else ""), file=sys.stderr)
    if plan["conf_globs"]:
        print(f"  confidential globs: {plan['conf_globs']}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scope", action="append", default=[],
                    help="glob to restrict reviewed files (repeatable; default: all tracked)")
    ap.add_argument("--paths", nargs="*", default=[],
                    help="explicit file list instead of git ls-files")
    ap.add_argument("--include-ext", action="append", default=[],
                    help="extra file extension to treat as reviewable, e.g. .md (repeatable)")
    ap.add_argument("--confidential-glob", action="append", default=[],
                    help="files matching this glob go to PAID privacy-ON agents "
                         "(repeatable; also LLM_FLEET_CONFIDENTIAL_GLOBS=a,b)")
    ap.add_argument("--files-per-worker", type=int, default=DEFAULT_FILES_PER_WORKER)
    ap.add_argument("--kb-per-worker", type=int, default=DEFAULT_KB_PER_WORKER)
    ap.add_argument("--max-workers", type=int, default=0, help="0 = unlimited")
    ap.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                    help=f"parallel API calls (default {DEFAULT_CONCURRENCY}, hard-capped at "
                         f"{MAX_CONCURRENCY}; higher fan-out triggers backend errors)")
    ap.add_argument("--max-words", type=int, default=400, help="word budget for the final report")
    ap.add_argument("--worker-runbook", default="review",
                    help="runbook each worker uses (default review; e.g. 'improve' for a "
                         "structure/quality pass)")
    ap.add_argument("--worker-max-words", type=int, default=220)
    ap.add_argument("--worker-timeout", type=int, default=420)
    ap.add_argument("--audit-timeout", type=int, default=420)
    ap.add_argument("--audit-no-privacy", action="store_true",
                    help="run the auditor on the FREE tier (only if findings hold no secrets)")
    ap.add_argument("--no-audit", action="store_true", help="skip the auditor pass (debug)")
    ap.add_argument("--out", default=None, help="write final report here "
                    "(default .llm_delegate/fleet_report.md)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit (no agents)")
    args = ap.parse_args()

    if not os.environ.get("OPENCODE_API_KEY") and not args.dry_run:
        return print("error: OPENCODE_API_KEY not set", file=sys.stderr) or 1

    root = repo_root()
    plan = build_plan(root, args)
    print_plan(plan)
    if args.dry_run:
        return 0
    if not plan["conf_chunks"] and not plan["open_chunks"]:
        print("error: no reviewable files in scope", file=sys.stderr)
        return 1

    jobs = ([("paid", c) for c in plan["conf_chunks"]]
            + [("free", c) for c in plan["open_chunks"]])
    conc = max(1, min(args.concurrency, MAX_CONCURRENCY))
    if args.concurrency > MAX_CONCURRENCY:
        print(f"[fleet] concurrency {args.concurrency} clamped to {MAX_CONCURRENCY} "
              f"(higher fan-out errors out)", file=sys.stderr)
    print(f"\n[fleet] dispatching {len(jobs)} worker agent(s) "
          f"(concurrency={conc}) …", file=sys.stderr)
    t0 = time.time()
    results: list[dict] = [None] * len(jobs)
    with futures.ThreadPoolExecutor(max_workers=conc) as ex:
        fut = {ex.submit(run_worker, root, chunk, tier == "paid",
                         args.worker_max_words, args.worker_timeout,
                         args.worker_runbook): i
               for i, (tier, chunk) in enumerate(jobs)}
        for f in futures.as_completed(fut):
            i = fut[f]
            tier, chunk = jobs[i]
            try:
                results[i] = f.result()
            except Exception as exc:  # noqa: BLE001
                results[i] = {"files": chunk, "paid": tier == "paid", "ok": False,
                              "findings": "", "err": str(exc)[-300:], "secs": 0,
                              "ptok": 0, "ctok": 0}
            r = results[i]
            print(f"  [{'PAID' if r['paid'] else 'free'}] "
                  f"{'ok ' if r['ok'] else 'ERR'} {len(chunk)}f {r['secs']}s "
                  f"{chunk[0]}{' …' if len(chunk) > 1 else ''}", file=sys.stderr)

    # merge worker findings into one document for the auditor
    blocks = []
    for r in results:
        tier = "PAID/confidential" if r["paid"] else "FREE/open"
        head = f"### worker [{tier}] files: {', '.join(r['files'])}"
        body = r["findings"] if r["ok"] and r["findings"] else f"(no findings / {r['err']})"
        blocks.append(f"{head}\n{body}")
    merged = "\n\n".join(blocks)

    w_pt = sum(r["ptok"] for r in results)
    w_ct = sum(r["ctok"] for r in results)
    n_ok = sum(1 for r in results if r["ok"])

    out_path = Path(args.out) if args.out else root / ".llm_delegate" / "fleet_report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.no_audit:
        final = merged
        a_pt = a_ct = 0
        raw_path = "(audit skipped)"
    else:
        print("\n[fleet] auditor agent reviewing merged findings …", file=sys.stderr)
        audit = run_auditor(merged, root, args.max_words, args.audit_timeout,
                            args.audit_no_privacy, args.worker_runbook)
        final = audit["report"] or f"(auditor produced no output / {audit['err']})"
        a_pt, a_ct = audit["ptok"], audit["ctok"]
        raw_path = audit["raw_path"]

    out_path.write_text(final + "\n", encoding="utf-8")
    elapsed = round(time.time() - t0, 1)

    # ── final report to stdout (this is all that comes back to the caller) ──
    print(final)
    print(f"\n[fleet] workers={len(jobs)} ok={n_ok} "
          f"paid={len(plan['conf_chunks'])} free={len(plan['open_chunks'])} "
          f"skipped_sensitive={len(plan['buckets']['skip'])} | "
          f"tokens worker={w_pt + w_ct} audit={a_pt + a_ct} | {elapsed}s | "
          f"report={out_path} raw={raw_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
