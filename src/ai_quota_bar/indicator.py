import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from ai_quota_bar.collector import collect_usage, get_cached_usage, deserialize_provider
from ai_quota_bar.config import load_config, CACHE_FILE, CONFIG_DIR, CONFIG_FILE

BUS_NAME = "org.kde.StatusNotifierItem-ai-quota-bar"
PID_FILE = os.path.expanduser("~/.cache/ai-quota-bar/indicator.pid")

def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False

def _kill_pid(pid: int):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(15):
        time.sleep(0.1)
        if not _is_pid_alive(pid):
            return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

def ensure_single_instance():
    """Find and terminate any existing instances of ai-quota-bar or ai-usage-monitor,
    ensuring only this instance runs and replacing any old instance."""
    my_pid = os.getpid()
    lock_dir = os.path.expanduser("~/.cache/ai-quota-bar")
    os.makedirs(lock_dir, exist_ok=True)

    # 1. Kill old PID from file if running
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            if old_pid != my_pid and _is_pid_alive(old_pid):
                _kill_pid(old_pid)
        except Exception:
            pass

    # 2. Scan /proc for any other running instances
    if os.path.exists("/proc"):
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == my_pid:
                continue
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read().decode("utf-8", "ignore").replace("\x00", " ")
                if ("ai-quota-bar" in cmd or "ai_quota_bar.indicator" in cmd or "ai-usage-monitor" in cmd) and not "grep" in cmd:
                    _kill_pid(pid)
            except (FileNotFoundError, PermissionError):
                continue

    # 3. Write our PID
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(my_pid))
    except Exception:
        pass

def get_status_dot(pct: Optional[int]) -> str:
    if pct is None:
        return "⚪"
    if pct >= 50:
        return "🟢"
    elif pct >= 20:
        return "🟡"
    else:
        return "🔴"

def render_progress_bar(pct: Optional[int], length: int = 10) -> str:
    if pct is None:
        return "[──────────]"
    pct = max(0, min(100, pct))
    filled = round((pct / 100) * length)
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}]"

def normalize_window_name(name: str, window_type: str = "") -> str:
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

def format_relative_time(iso_str):
    if not iso_str:
        return ""
    try:
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        diff = dt - now
        total_seconds = int(diff.total_seconds())
        if total_seconds <= 0:
            return "(resets now)"
        hours = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        if hours >= 24:
            days = hours // 24
            rem_h = hours % 24
            return f"(in {days}d {rem_h}h)"
        if hours > 0:
            return f"(in {hours}h {mins}m)"
        return f"(in {mins}m)"
    except Exception:
        return ""

class DBusMenu(dbus.service.Object):
    def __init__(self, bus, on_refresh=None, on_quit=None, on_open_config=None):
        super().__init__(bus, "/MenuBar")
        self.revision = 1
        self.on_refresh = on_refresh
        self.on_quit = on_quit
        self.on_open_config = on_open_config
        self.items = []
        self.item_props = {}
        self.callbacks = {}

    def update_menu(self, data):
        self.revision += 1
        self.callbacks.clear()
        self.item_props.clear()
        new_items = []

        item_id = 1

        def add_item(label, enabled=True, on_click=None, icon_name=None):
            nonlocal item_id
            cid = item_id
            item_id += 1
            if on_click:
                self.callbacks[cid] = on_click
            props = {
                "label": dbus.String(label),
                "enabled": dbus.Boolean(enabled),
            }
            if icon_name:
                props["icon-name"] = dbus.String(icon_name)
                png_path = os.path.expanduser(f"~/.local/share/icons/hicolor/24x24/apps/{icon_name}.png")
                if os.path.exists(png_path):
                    try:
                        with open(png_path, "rb") as f:
                            props["icon-data"] = dbus.ByteArray(f.read())
                    except Exception:
                        pass
            self.item_props[cid] = props
            struct = dbus.Struct(
                (dbus.Int32(cid), dbus.Dictionary(props, signature="sv"), dbus.Array([], signature="v")),
                signature="(ia{sv}av)",
                variant_level=1
            )
            new_items.append(struct)

        def add_separator():
            nonlocal item_id
            cid = item_id
            item_id += 1
            props = {"type": dbus.String("separator")}
            self.item_props[cid] = props
            struct = dbus.Struct(
                (dbus.Int32(cid), dbus.Dictionary(props, signature="sv"), dbus.Array([], signature="v")),
                signature="(ia{sv}av)",
                variant_level=1
            )
            new_items.append(struct)

        add_item("── AI Quota & Usage Monitor ──", enabled=False, icon_name="ai-quota-bar")
        add_separator()

        providers_raw = data.get("providers", {})
        for pid, pdata in providers_raw.items():
            p = deserialize_provider(pdata)

            # Header with clean name and logo icon - NO EMOJIS!
            header = p.display_name
            if p.plan_name:
                header += f" ({p.plan_name})"
            add_item(header, enabled=False, icon_name=pid)

            if not p.ok:
                add_item(f"   ⚠️ {p.error or 'Error'}", enabled=False)
            else:
                sorted_windows = sorted(p.windows, key=sort_window_key)
                for w in sorted_windows:
                    norm_name = normalize_window_name(w.name, w.window_type)
                    pct_val = w.remaining_pct if w.remaining_pct is not None else "--"
                    pct_str = f"{pct_val:>3}%"
                    bar = render_progress_bar(w.remaining_pct, length=10)
                    reset_str = format_relative_time(w.resets_at)
                    line = f"   {norm_name:<13} {pct_str}  {bar}"
                    if reset_str:
                        line += f"  {reset_str}"
                    add_item(line, enabled=False)

                sub_groups = [sg for sg in p.sub_groups if sg.group_name != "Gemini Models"]
                for i, sg in enumerate(sub_groups):
                    is_last = (i == len(sub_groups) - 1)
                    tree_char = "└──" if is_last else "├──"
                    parts = []
                    sorted_sg_windows = sorted(sg.windows, key=sort_window_key)
                    for w in sorted_sg_windows:
                        w_short = "5h" if ("5h" in w.name.lower() or "five" in w.name.lower()) else ("W" if "week" in w.name.lower() else "Limit")
                        pct_s = f"{w.remaining_pct}%" if w.remaining_pct is not None else "--"
                        reset_s = format_relative_time(w.resets_at)
                        part = f"{w_short} {pct_s}"
                        if reset_s:
                            part += f" {reset_s}"
                        parts.append(part)
                    sub_line = f"   {tree_char} {sg.group_name}: " + "  •  ".join(parts)
                    add_item(sub_line, enabled=False)

            add_separator()

        ts = data.get("timestamp")
        time_str = "most"
        if ts:
            try:
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                dt = datetime.fromisoformat(ts).astimezone()
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                pass
        add_item(f"🕒 Frissítve: {time_str}", enabled=False)

        if self.on_refresh:
            add_item("🔄 Frissítés most (Refresh)", enabled=True, on_click=self.on_refresh)

        if self.on_open_config:
            add_item("⚙️ Beállítások (Config)", enabled=True, on_click=self.on_open_config)

        if self.on_quit:
            add_item("❌ Kilépés (Quit)", enabled=True, on_click=self.on_quit)

        self.items = new_items
        self.LayoutUpdated(dbus.UInt32(self.revision), dbus.Int32(0))

    @dbus.service.signal("com.canonical.dbusmenu", signature="ui")
    def LayoutUpdated(self, revision, parent):
        pass

    @dbus.service.method("com.canonical.dbusmenu", in_signature="iias", out_signature="u(ia{sv}av)")
    def GetLayout(self, parentId, recursionDepth, propertyNames):
        root_props = dbus.Dictionary({"children-display": dbus.String("submenu")}, signature="sv")
        children = dbus.Array(self.items, signature="v")
        root = dbus.Struct((dbus.Int32(0), root_props, children), signature="(ia{sv}av)")
        return (dbus.UInt32(self.revision), root)

    @dbus.service.method("com.canonical.dbusmenu", in_signature="aias", out_signature="a(ia{sv})")
    def GetGroupProperties(self, ids, propertyNames):
        result = []
        target_ids = ids if ids else list(self.item_props.keys())
        for cid in target_ids:
            if cid in self.item_props:
                dict_props = dbus.Dictionary(self.item_props[cid], signature="sv")
                result.append(dbus.Struct((dbus.Int32(cid), dict_props), signature="(ia{sv})"))
        return dbus.Array(result, signature="(ia{sv})")

    @dbus.service.method("com.canonical.dbusmenu", in_signature="is", out_signature="v")
    def GetProperty(self, item_id, name):
        if item_id in self.item_props and name in self.item_props[item_id]:
            return self.item_props[item_id][name]
        return dbus.String("", variant_level=1)

    @dbus.service.method("com.canonical.dbusmenu", in_signature="isvu")
    def Event(self, item_id, eventId, data, timestamp):
        if eventId == "clicked" and item_id in self.callbacks:
            self.callbacks[item_id]()

    @dbus.service.method("com.canonical.dbusmenu", in_signature="i", out_signature="b")
    def AboutToShow(self, item_id):
        return False

class StatusNotifierItem(dbus.service.Object):
    def __init__(self, conn, provider_id, icon_name):
        super().__init__(conn, "/StatusNotifierItem")
        self.provider_id = provider_id
        self.icon_name = icon_name
        self.label = ""
        self.icon_theme_path = os.path.expanduser("~/.local/share/icons")

    def set_label(self, label):
        self.label = label
        self.XAyatanaNewLabel(dbus.String(self.label), dbus.String(self.label))

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        props = self.GetAll(interface)
        return props.get(prop, "")

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == "org.kde.StatusNotifierItem":
            return {
                "Category": dbus.String("ApplicationStatus"),
                "Id": dbus.String(f"ai-quota-{self.provider_id}"),
                "Title": dbus.String(f"AI Quota ({self.provider_id})"),
                "Status": dbus.String("Active"),
                "IconName": dbus.String(self.icon_name),
                "IconThemePath": dbus.String(self.icon_theme_path),
                "Menu": dbus.ObjectPath("/MenuBar"),
                "XAyatanaLabel": dbus.String(self.label),
                "XAyatanaLabelGuide": dbus.String("5h 100% W 100%"),
                "XAyatanaOrderingIndex": dbus.UInt32(0),
            }
        return {}

    @dbus.service.signal("org.kde.StatusNotifierItem", signature="ss")
    def XAyatanaNewLabel(self, label, guide):
        pass

    @dbus.service.signal("org.kde.StatusNotifierItem", signature="s")
    def NewStatus(self, status):
        pass

    def quit(self):
        try:
            self.NewStatus("Passive")
        except Exception:
            pass

class ProviderIndicator:
    def __init__(self, provider_id, icon_name, on_refresh, on_quit, on_open_config):
        self.provider_id = provider_id
        self.icon_name = icon_name
        self.bus_name_str = f"org.kde.StatusNotifierItem-ai-quota-{provider_id}"
        self.conn = dbus.bus.BusConnection(dbus.Bus.TYPE_SESSION)
        self.bus_name = dbus.service.BusName(
            self.bus_name_str,
            self.conn,
            replace_existing=True,
            do_not_queue=True
        )
        self.menu = DBusMenu(self.conn, on_refresh=on_refresh, on_quit=on_quit, on_open_config=on_open_config)
        self.item = StatusNotifierItem(self.conn, self.provider_id, self.icon_name)

class App:
    def __init__(self):
        ensure_single_instance()

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.loop = GLib.MainLoop()
        self.cfg = load_config()

        self.indicators = {}
        target_provs = ["claude", "antigravity", "codex", "copilot"]

        for pid in target_provs:
            self.indicators[pid] = ProviderIndicator(
                provider_id=pid,
                icon_name=pid,
                on_refresh=self.trigger_refresh,
                on_quit=self.quit,
                on_open_config=self.open_config
            )

        self._register_with_watcher()
        GLib.timeout_add_seconds(3, self._check_watcher_registration)

        self._refreshing = False
        self.load_cache()
        self.trigger_refresh()

        interval = int(self.cfg.get("update_interval_seconds", 120))
        GLib.timeout_add_seconds(interval, self._on_timer)

        for sig in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, self._on_signal_exit, sig)

    def _register_with_watcher(self):
        try:
            session_bus = dbus.SessionBus()
            watcher = session_bus.get_object("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher")
            for pid, ind in self.indicators.items():
                watcher.RegisterStatusNotifierItem(ind.bus_name_str, dbus_interface="org.kde.StatusNotifierWatcher")
        except Exception:
            pass

    def _check_watcher_registration(self):
        self._register_with_watcher()
        return GLib.SOURCE_REMOVE

    def _on_signal_exit(self, sig):
        self.quit()
        return GLib.SOURCE_REMOVE

    def load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.update_data(data)
            except Exception:
                pass

    def open_config(self):
        try:
            subprocess.Popen(["xdg-open", CONFIG_FILE])
        except Exception:
            pass

    def update_data(self, data: dict):
        providers_raw = data.get("providers", {})
        fmt = self.cfg.get("topbar_format", "standard")

        for pid, ind in self.indicators.items():
            ind.menu.update_menu(data)

            pdata = providers_raw.get(pid)
            if not pdata:
                ind.item.set_label("")
                continue
            p = deserialize_provider(pdata)
            if not p.ok:
                ind.item.set_label("err")
                continue

            w5 = p.get_5h_window()
            wW = p.get_weekly_window()

            if fmt == "compact":
                s5 = f"{w5.remaining_pct}%" if w5 and w5.remaining_pct is not None else "--"
                sW = f"{wW.remaining_pct}%" if wW and wW.remaining_pct is not None else "--"
                if w5 and wW:
                    ind.item.set_label(f"{s5}·{sW}")
                elif wW:
                    ind.item.set_label(f"{sW}")
                elif w5:
                    ind.item.set_label(f"{s5}")
                elif p.windows:
                    first_pct = p.windows[0].remaining_pct
                    ind.item.set_label(f"{first_pct}%" if first_pct is not None else "ok")
            else:
                sub_parts = []
                if w5 and w5.remaining_pct is not None:
                    sub_parts.append(f"5h {w5.remaining_pct}%")
                if wW and wW.remaining_pct is not None:
                    sub_parts.append(f"W {wW.remaining_pct}%")

                if sub_parts:
                    ind.item.set_label(" ".join(sub_parts))
                elif p.windows and p.windows[0].remaining_pct is not None:
                    ind.item.set_label(f"{p.windows[0].remaining_pct}%")
                else:
                    ind.item.set_label("ok")

    def _on_timer(self):
        self.trigger_refresh()
        return GLib.SOURCE_CONTINUE

    def trigger_refresh(self):
        if self._refreshing:
            return
        self._refreshing = True

        for ind in self.indicators.values():
            curr = ind.item.label.replace(" ⟳", "")
            ind.item.set_label(f"{curr} ⟳")

        GLib.timeout_add_seconds(15, self._on_refresh_timeout)

        def worker():
            try:
                res = collect_usage(force=True)
                GLib.idle_add(self._on_refresh_done, res)
            except Exception as e:
                print(f"Error in refresh worker: {e}", file=sys.stderr)
                GLib.idle_add(self._on_refresh_failed)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_refresh_timeout(self):
        if self._refreshing:
            self._refreshing = False
            for ind in self.indicators.values():
                curr = ind.item.label.replace(" ⟳", "")
                ind.item.set_label(curr)
        return GLib.SOURCE_REMOVE

    def _on_refresh_done(self, res):
        self._refreshing = False
        self.update_data(res)
        return GLib.SOURCE_REMOVE

    def _on_refresh_failed(self):
        self._refreshing = False
        for ind in self.indicators.values():
            curr = ind.item.label.replace(" ⟳", "")
            ind.item.set_label(curr)
        return GLib.SOURCE_REMOVE

    def quit(self):
        for ind in self.indicators.values():
            ind.item.quit()
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
        self.loop.quit()

    def run(self):
        self.loop.run()

def main():
    app = App()
    app.run()

if __name__ == "__main__":
    main()
