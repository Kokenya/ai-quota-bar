import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from ai_quota_bar.collector import collect_usage, get_cached_usage, deserialize_provider
from ai_quota_bar.config import CACHE_FILE

def str_width(s):
    clean = re.sub(r'\033\[[0-9;]*m', '', s)
    return sum(2 if unicodedata.east_asian_width(c) in ('F', 'W') else 1 for c in clean)

def pad_to_width(s, width):
    w = str_width(s)
    if w < width:
        return s + ' ' * (width - w)
    return s

def format_relative_time(iso_str):
    if not iso_str:
        return "-"
    try:
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        diff = dt - now
        total_seconds = int(diff.total_seconds())
        if total_seconds <= 0:
            return "resets now"
        hours = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        if hours >= 24:
            days = hours // 24
            rem_h = hours % 24
            return f"in {days}d {rem_h}h"
        if hours > 0:
            return f"in {hours}h {mins}m"
        return f"in {mins}m"
    except Exception:
        return "-"

def normalize_window_name(name, window_type=""):
    nl = name.strip().lower()
    wt = (window_type or "").lower()
    if "five hour" in nl or "5-hour" in nl or "5h" in nl or wt == "5h":
        return "5-Hour Limit"
    if "weekly" in nl or "7-day" in nl or "seven day" in nl or wt == "weekly" or "week" in nl:
        return "Weekly Limit"
    if "hourly" in nl or wt == "hourly":
        return "Hourly Limit"
    if "monthly" in nl or "plan quota" in nl or wt == "monthly":
        return "Monthly Limit"
    if nl.endswith(" remaining"):
        return name[:-10].strip()
    return name

def sort_window_key(w):
    nl = (w.name or "").strip().lower()
    wt = (w.window_type or "").lower()
    if wt == "5h" or "five hour" in nl or "5-hour" in nl or "5h" in nl:
        return 1
    if wt == "weekly" or "7-day" in nl or "seven day" in nl or "week" in nl:
        return 2
    if wt == "hourly" or "hour" in nl:
        return 3
    if wt == "monthly" or "month" in nl or "plan" in nl:
        return 4
    return 5

def cli_progress_bar(pct, length=10, use_colors=True):
    if pct is None:
        bar = "[──────────]"
        return f"\033[90m{bar}\033[0m" if use_colors else bar
    pct = max(0, min(100, pct))
    filled = round((pct / 100) * length)
    empty = length - filled
    bar_str = f"[{'█' * filled}{'░' * empty}]"
    if not use_colors:
        return bar_str
    if pct >= 50:
        return f"\033[92m{bar_str}\033[0m"
    elif pct >= 20:
        return f"\033[93m{bar_str}\033[0m"
    else:
        return f"\033[91m{bar_str}\033[0m"

def color_pct(pct, use_colors=True):
    if pct is None:
        return "--" if not use_colors else "\033[90m--\033[0m"
    s = f"{pct:>3}%"
    if not use_colors:
        return s
    if pct >= 50:
        return f"\033[92m{s}\033[0m"
    elif pct >= 20:
        return f"\033[93m{s}\033[0m"
    else:
        return f"\033[91m{s}\033[0m"

def render_cli(data, use_colors=True):
    providers_raw = data.get("providers", {})

    c_cyan = "\033[1;36m" if use_colors else ""
    c_white = "\033[1;37m" if use_colors else ""
    c_yellow = "\033[1;33m" if use_colors else ""
    c_blue = "\033[1;34m" if use_colors else ""
    c_purple = "\033[1;35m" if use_colors else ""
    c_green = "\033[1;32m" if use_colors else ""
    c_reset = "\033[0m" if use_colors else ""

    print(f"{c_cyan}========================================================================================{c_reset}")
    print(f"{c_white}                               AI QUOTA & USAGE MONITOR                                 {c_reset}")
    print(f"{c_cyan}========================================================================================{c_reset}")
    print(f"{c_yellow}PROVIDER / MODEL GROUP            LIMIT TYPE       REMAINING    PROGRESS       RESETS IN{c_reset}")
    print("----------------------------------------------------------------------------------------")

    for pid, pdata in providers_raw.items():
        p = deserialize_provider(pdata)
        color = c_purple if pid == "claude" else (c_blue if pid == "antigravity" else (c_green if pid == "codex" else c_cyan))
        name_str = p.display_name
        if p.plan_name:
            name_str += f" ({p.plan_name})"

        if not p.ok:
            err_msg = p.error or "Error"
            padded_hdr = pad_to_width(name_str, 33)
            print(f"{color}{padded_hdr}{c_reset} {err_msg[:50]}")
            print("----------------------------------------------------------------------------------------")
            continue

        sorted_windows = sorted(p.windows, key=sort_window_key)
        if sorted_windows:
            for idx, w in enumerate(sorted_windows):
                prefix = f"{color}{pad_to_width(name_str, 33)}{c_reset}" if idx == 0 else " " * 33
                norm_name = normalize_window_name(w.name, w.window_type)
                pct_str = color_pct(w.remaining_pct, use_colors)
                bar_str = cli_progress_bar(w.remaining_pct, 10, use_colors)
                reset_str = format_relative_time(w.resets_at)
                print(f"{prefix} {norm_name:<16} {pct_str}      {bar_str}    {reset_str:<12}")

        sub_groups = [sg for sg in p.sub_groups if sg.group_name != "Gemini Models"]
        if sub_groups:
            for s_idx, sg in enumerate(sub_groups):
                is_last_sg = (s_idx == len(sub_groups) - 1)
                tree_symbol = "└──" if is_last_sg else "├──"
                pipe_symbol = "   " if is_last_sg else "│  "
                sorted_sg_windows = sorted(sg.windows, key=sort_window_key)
                for idx, w in enumerate(sorted_sg_windows):
                    raw_sg = f"  {tree_symbol} {sg.group_name}" if idx == 0 else f"  {pipe_symbol}"
                    sg_name = pad_to_width(raw_sg, 33)
                    norm_name = normalize_window_name(w.name, w.window_type)
                    pct_str = color_pct(w.remaining_pct, use_colors)
                    bar_str = cli_progress_bar(w.remaining_pct, 10, use_colors)
                    reset_str = format_relative_time(w.resets_at)
                    print(f"{sg_name} {norm_name:<16} {pct_str}      {bar_str}    {reset_str:<12}")

        print("----------------------------------------------------------------------------------------")

    ts = data.get("timestamp", "")
    if ts:
        try:
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            dt = datetime.fromisoformat(ts).astimezone()
            print(f"Updated: {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except Exception:
            pass
    print(f"{c_cyan}========================================================================================{c_reset}")

def main():
    parser = argparse.ArgumentParser(description="AI Coding CLI Usage & Quota Monitor")
    parser.add_argument("-r", "--refresh", action="store_true", help="Force immediate refresh of all quotas")
    parser.add_argument("-j", "--json", action="store_true", help="Output raw JSON data")
    parser.add_argument("-w", "--watch", type=int, nargs="?", const=5, help="Watch mode: refresh every N seconds (default 5)")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")

    args = parser.parse_args()

    use_colors = not args.no_color and sys.stdout.isatty()

    if args.watch:
        try:
            while True:
                os.system("clear" if os.name == "posix" else "cls")
                data = collect_usage(force=True)
                if args.json:
                    print(json.dumps(data, indent=2))
                else:
                    render_cli(data, use_colors=use_colors)
                time.sleep(args.watch)
        except KeyboardInterrupt:
            sys.exit(0)

    if args.refresh or not os.path.exists(CACHE_FILE):
        data = collect_usage(force=True)
    else:
        data = get_cached_usage()

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        render_cli(data, use_colors=use_colors)

if __name__ == "__main__":
    main()
