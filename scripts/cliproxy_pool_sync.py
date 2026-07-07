#!/usr/bin/env python3
import argparse
import json
import os
import random
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_MAIN_DIR = Path.home() / ".cli-proxy-api-main"
DEFAULT_WORK_DIR = Path.home() / ".cli-proxy-api"
DEFAULT_STATE_FILE = Path.home() / ".codex" / "cliproxy-pool-state.json"
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_iso(ts: str):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)


def is_account_file(path: Path) -> bool:
    return path.suffix == ".json" and path.name not in {"accounts.json", "config.yaml"}


def list_account_files(directory: Path):
    if not directory.exists():
        return []
    return sorted([p for p in directory.iterdir() if p.is_file() and is_account_file(p)])


def init_main_pool(main_dir: Path, work_dir: Path) -> int:
    if main_dir.exists() and list_account_files(main_dir):
        return 0
    main_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in list_account_files(work_dir):
        shutil.copy2(path, main_dir / path.name)
        copied += 1
    return copied


def load_account(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_account(path: Path, account: dict) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(account, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def normalize_selected_account(account: dict) -> dict:
    normalized = dict(account)
    # Selected accounts must stay enabled in the live work pool.
    normalized["disabled"] = False
    return normalized


def account_score(state_entry: dict) -> tuple:
    cooldown_until = parse_iso(state_entry.get("cooldown_until", "")) if state_entry else None
    cooling = 1 if cooldown_until and cooldown_until > utc_now() else 0
    failures = int(state_entry.get("consecutive_failures", 0)) if state_entry else 0
    last_success = parse_iso(state_entry.get("last_success_at", "")) if state_entry else None
    last_success_ts = -(last_success.timestamp()) if last_success else float("inf")
    return (cooling, failures, last_success_ts)


def direct_probe(account: dict, timeout: int):
    token = str(account.get("access_token") or "").strip()
    if not token:
        return False, "missing access_token", None

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "cliproxy-pool-sync/1.0",
    }
    account_id = str(account.get("account_id") or "").strip()
    if account_id:
        headers["Chatgpt-Account-Id"] = account_id

    req = urllib.request.Request(USAGE_URL, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            body = resp.read(4096).decode("utf-8", "replace")
            data = json.loads(body)
            rate_limit = data.get("rate_limit", {}) if isinstance(data, dict) else {}
            allowed = rate_limit.get("allowed", True)
            limit_reached = rate_limit.get("limit_reached", False)
            if allowed is False or limit_reached is True:
                return False, "quota_exhausted", data
            return True, "ok", data
    except urllib.error.HTTPError as exc:
        try:
            payload = exc.read().decode("utf-8", "replace")
        except Exception:
            payload = ""
        reason = f"http_{exc.code}"
        if exc.code in (401, 403):
            reason = "auth_invalid"
        elif exc.code == 429:
            reason = "quota_exhausted"
        return False, f"{reason}:{payload[:200]}", None
    except Exception as exc:
        return False, f"{type(exc).__name__}:{str(exc)[:200]}", None


def compute_cooldown_seconds(failures: int) -> int:
    if failures <= 1:
        return 300
    if failures == 2:
        return 1800
    if failures == 3:
        return 7200
    return 21600


def copy_selected(selected_paths, work_dir: Path):
    work_dir.mkdir(parents=True, exist_ok=True)
    keep_names = {p.name for p in selected_paths}
    before_names = {p.name for p in list_account_files(work_dir)}
    changed = before_names != keep_names
    for path in list_account_files(work_dir):
        if path.name not in keep_names:
            path.unlink(missing_ok=True)
    entries = []
    for src in selected_paths:
        dst = work_dir / src.name
        try:
            normalized = normalize_selected_account(load_account(src))
        except Exception:
            pass
            continue

        existing = None
        if dst.exists():
            try:
                existing = load_account(dst)
            except Exception:
                existing = None
        if existing != normalized:
            changed = True
        write_account(dst, normalized)
        entries.append(normalized)
    accounts_path = work_dir / "accounts.json"
    old_accounts = ""
    if accounts_path.exists():
        old_accounts = accounts_path.read_text(encoding="utf-8")
    new_accounts = json.dumps(entries, ensure_ascii=False, indent=2)
    if old_accounts != new_accounts:
        changed = True
    with accounts_path.open("w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=2)
    return changed


def sync(main_dir: Path, work_dir: Path, state_path: Path, target_size: int, probe_limit: int, timeout: int):
    state = load_state(state_path)
    copied = init_main_pool(main_dir, work_dir)
    source_files = list_account_files(main_dir)
    if not source_files:
        raise SystemExit(f"no account json files found in main pool: {main_dir}")

    ranked = []
    for path in source_files:
        ranked.append((account_score(state.get(path.name, {})), path))
    ranked.sort(key=lambda item: item[0])

    selected = []
    inspected = 0
    for _, path in ranked:
        if len(selected) >= target_size or inspected >= probe_limit:
            break
        entry = state.get(path.name, {})
        cooldown_until = parse_iso(entry.get("cooldown_until", ""))
        if cooldown_until and cooldown_until > utc_now():
            continue
        try:
            account = load_account(path)
        except Exception as exc:
            state[path.name] = {
                **entry,
                "last_checked_at": iso_now(),
                "last_error": f"json_decode:{exc}",
                "consecutive_failures": int(entry.get("consecutive_failures", 0)) + 1,
                "cooldown_until": (utc_now()).isoformat(),
            }
            continue

        if not all(account.get(k) for k in ("access_token", "refresh_token", "account_id")):
            failures = int(entry.get("consecutive_failures", 0)) + 1
            state[path.name] = {
                **entry,
                "last_checked_at": iso_now(),
                "last_error": "missing_required_fields",
                "consecutive_failures": failures,
                "cooldown_until": (utc_now()).isoformat(),
            }
            continue

        ok, reason, payload = direct_probe(account, timeout)
        inspected += 1
        if ok:
            state[path.name] = {
                **entry,
                "last_checked_at": iso_now(),
                "last_success_at": iso_now(),
                "last_error": "",
                "consecutive_failures": 0,
                "cooldown_until": "",
                "last_probe_summary": payload.get("rate_limit", {}) if isinstance(payload, dict) else {},
            }
            selected.append(path)
        else:
            failures = int(entry.get("consecutive_failures", 0)) + 1
            cooldown_seconds = compute_cooldown_seconds(failures)
            state[path.name] = {
                **entry,
                "last_checked_at": iso_now(),
                "last_error": reason,
                "consecutive_failures": failures,
                "cooldown_until": datetime.fromtimestamp(time.time() + cooldown_seconds, tz=timezone.utc).isoformat(),
            }

    if not selected:
        raise SystemExit("sync failed: no healthy accounts selected from main pool")

    if len(selected) < target_size:
        remaining = [p for p in source_files if p not in selected]
        random.shuffle(remaining)
        for path in remaining:
            if len(selected) >= target_size:
                break
            selected.append(path)

    work_pool_changed = copy_selected(selected, work_dir)
    save_state(state_path, state)

    return {
        "initialized_main_pool": copied,
        "source_total": len(source_files),
        "probed": inspected,
        "selected": len(selected),
        "work_pool_changed": work_pool_changed,
        "main_dir": str(main_dir),
        "work_dir": str(work_dir),
        "state_file": str(state_path),
    }


def status(main_dir: Path, work_dir: Path, state_path: Path):
    state = load_state(state_path)
    now = utc_now()
    cooling = 0
    for item in state.values():
        cooldown_until = parse_iso(item.get("cooldown_until", ""))
        if cooldown_until and cooldown_until > now:
            cooling += 1
    return {
        "main_pool_count": len(list_account_files(main_dir)),
        "work_pool_count": len(list_account_files(work_dir)),
        "cooling_accounts": cooling,
        "state_file": str(state_path),
        "main_dir": str(main_dir),
        "work_dir": str(work_dir),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["sync", "status", "init-main"])
    parser.add_argument("--main-dir", default=str(DEFAULT_MAIN_DIR))
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--target-size", type=int, default=24)
    parser.add_argument("--probe-limit", type=int, default=36)
    parser.add_argument("--timeout", type=int, default=12)
    args = parser.parse_args()

    main_dir = Path(os.path.expanduser(args.main_dir))
    work_dir = Path(os.path.expanduser(args.work_dir))
    state_path = Path(os.path.expanduser(args.state_file))

    if args.command == "init-main":
        copied = init_main_pool(main_dir, work_dir)
        print(json.dumps({"initialized_main_pool": copied, "main_dir": str(main_dir)}, ensure_ascii=False))
        return
    if args.command == "status":
        print(json.dumps(status(main_dir, work_dir, state_path), ensure_ascii=False))
        return

    result = sync(main_dir, work_dir, state_path, args.target_size, args.probe_limit, args.timeout)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
