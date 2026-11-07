import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from ai_quota_bar.collector import collect_usage, get_cached_usage, deserialize_provider
from ai_quota_bar.config import CACHE_FILE

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

def color_pct(pct, use_colors=True):
    if pct is None:
        return "--" if not use_colors else "\033[90m--\033[0m"
    s = f"{pct:>3}%"
    if not use_colors:
        return s
    if pct > 40:
        return f"\033[92m{s}\033[0m"
    elif pct > 15:
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

    print(f"{c_cyan}========================================================================{c_reset}")
    print(f"{c_white}                     AI QUOTA & USAGE MONITOR                           {c_reset}")
    print(f"{c_cyan}========================================================================{c_reset}")
    print(f"{c_yellow}PROVIDER / MODEL GROUP            LIMIT TYPE      REMAINING    RESETS IN{c_reset}")
    print("------------------------------------------------------------------------")

    for pid, pdata in providers_raw.items():
        p = deserialize_provider(pdata)
        color = c_purple if pid == "claude" else (c_blue if pid == "antigravity" else c_green)
        name_str = f"{p.icon} {p.display_name}"
        if p.plan_name:
            name_str += f" ({p.plan_name})"

        if not p.ok:
            err_msg = p.error or "Error"
            print(f"{color}{name_str:<32}{c_reset} {err_msg[:38]}")
            print("------------------------------------------------------------------------")
            continue

        if p.windows:
            for idx, w in enumerate(p.windows):
                prefix = f"{color}{name_str:<32}{c_reset}" if idx == 0 else " " * 32
                pct_str = color_pct(w.remaining_pct, use_colors)
                reset_str = format_relative_time(w.resets_at)
                print(f"{prefix} {w.name:<15} {pct_str}        {reset_str:<12}")

        if p.sub_groups:
            for sg in p.sub_groups:
                if sg.group_name == "Gemini Models" and p.windows:
                    continue  # already printed in main windows
                for idx, w in enumerate(sg.windows):
                    sg_name = f"  └ {sg.group_name}" if idx == 0 else ""
                    pct_str = color_pct(w.remaining_pct, use_colors)
                    reset_str = format_relative_time(w.resets_at)
                    print(f"{sg_name:<32} {w.name:<15} {pct_str}        {reset_str:<12}")

        print("------------------------------------------------------------------------")

    ts = data.get("timestamp", "")
    if ts:
        try:
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            dt = datetime.fromisoformat(ts).astimezone()
            print(f"Updated: {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except Exception:
            pass
    print(f"{c_cyan}========================================================================{c_reset}")

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
