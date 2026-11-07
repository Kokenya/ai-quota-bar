import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import json
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone

from ai_quota_bar.collector import collect_usage, get_cached_usage, deserialize_provider
from ai_quota_bar.config import load_config, CACHE_FILE, CONFIG_DIR

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
    def __init__(self, bus, on_refresh=None, on_quit=None):
        super().__init__(bus, "/MenuBar")
        self.revision = 1
        self.on_refresh = on_refresh
        self.on_quit = on_quit
        self.items = []
        self.callbacks = {}

    def update_menu(self, data):
        self.revision += 1
        self.callbacks.clear()
        new_items = []

        item_id = 1

        def add_item(label, enabled=True, on_click=None):
            nonlocal item_id
            cid = item_id
            item_id += 1
            if on_click:
                self.callbacks[cid] = on_click
            props = {
                "label": dbus.String(label),
                "enabled": dbus.Boolean(enabled),
            }
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
            struct = dbus.Struct(
                (dbus.Int32(cid), dbus.Dictionary(props, signature="sv"), dbus.Array([], signature="v")),
                signature="(ia{sv}av)",
                variant_level=1
            )
            new_items.append(struct)

        add_item("── AI Quota & Usage Monitor ──", enabled=False)
        add_separator()

        providers_raw = data.get("providers", {})
        for pid, pdata in providers_raw.items():
            p = deserialize_provider(pdata)
            header = f"{p.icon} {p.display_name}"
            if p.plan_name:
                header += f" ({p.plan_name})"
            header += ":"
            add_item(header, enabled=False)

            if not p.ok:
                add_item(f"   ⚠️ {p.error or 'Error'}", enabled=False)
            else:
                for w in p.windows:
                    rem_str = f"{w.remaining_pct}%" if w.remaining_pct is not None else "--"
                    reset_str = format_relative_time(w.resets_at)
                    add_item(f"   ⏱️ {w.name}: {rem_str} left {reset_str}".strip(), enabled=False)

                for sg in p.sub_groups:
                    if sg.group_name == "Gemini Models":
                        continue
                    add_item(f"   [{sg.group_name}]", enabled=False)
                    for w in sg.windows:
                        rem_str = f"{w.remaining_pct}%" if w.remaining_pct is not None else "--"
                        reset_str = format_relative_time(w.resets_at)
                        add_item(f"     • {w.name}: {rem_str} left {reset_str}".strip(), enabled=False)

            add_separator()

        ts = data.get("timestamp")
        time_str = "just now"
        if ts:
            try:
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                dt = datetime.fromisoformat(ts).astimezone()
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                pass
        add_item(f"🕒 Updated: {time_str}", enabled=False)

        if self.on_refresh:
            add_item("🔄 Refresh Now", enabled=True, on_click=self.on_refresh)

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
        return dbus.Array([], signature="(ia{sv})")

    @dbus.service.method("com.canonical.dbusmenu", in_signature="is", out_signature="v")
    def GetProperty(self, item_id, name):
        return dbus.String("", variant_level=1)

    @dbus.service.method("com.canonical.dbusmenu", in_signature="isvu")
    def Event(self, item_id, eventId, data, timestamp):
        if eventId == "clicked" and item_id in self.callbacks:
            self.callbacks[item_id]()

    @dbus.service.method("com.canonical.dbusmenu", in_signature="i", out_signature="b")
    def AboutToShow(self, item_id):
        return False

class StatusNotifierItem(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, "/StatusNotifierItem")
        self.label = "AI Quota..."
        self.icon_name = "utilities-system-monitor-symbolic"

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
                "Id": dbus.String("ai-quota-bar"),
                "Title": dbus.String("AI Quota Bar"),
                "Status": dbus.String("Active"),
                "IconName": dbus.String(self.icon_name),
                "IconThemePath": dbus.String(""),
                "Menu": dbus.ObjectPath("/MenuBar"),
                "XAyatanaLabel": dbus.String(self.label),
                "XAyatanaLabelGuide": dbus.String("C: 5h 100% W 100% | AG: 5h 100% W 100%"),
                "XAyatanaOrderingIndex": dbus.UInt32(0),
            }
        return {}

    @dbus.service.signal("org.kde.StatusNotifierItem", signature="ss")
    def XAyatanaNewLabel(self, label, guide):
        pass

    @dbus.service.signal("org.kde.StatusNotifierItem", signature="s")
    def NewStatus(self, status):
        pass

class App:
    def __init__(self):
        # 1. Kill any existing instances before registering
        ensure_single_instance()

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus()
        self.bus_name = dbus.service.BusName(
            BUS_NAME,
            self.bus,
            replace_existing=True,
            do_not_queue=True
        )
        self.loop = GLib.MainLoop()

        self.cfg = load_config()
        self.menu = DBusMenu(self.bus, on_refresh=self.trigger_refresh, on_quit=self.quit)
        self.item = StatusNotifierItem(self.bus)

        self._register_with_watcher()
        # Retry registration if watcher becomes available later
        GLib.timeout_add_seconds(3, self._check_watcher_registration)

        self._refreshing = False

        # Load initial cached state
        self.load_cache()

        # Initial background refresh
        self.trigger_refresh()

        # Timer
        interval = int(self.cfg.get("update_interval_seconds", 120))
        GLib.timeout_add_seconds(interval, self._on_timer)

        # Clean exit on signals
        for sig in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, self._on_signal_exit, sig)

    def _register_with_watcher(self):
        try:
            watcher = self.bus.get_object("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher")
            watcher.RegisterStatusNotifierItem(BUS_NAME, dbus_interface="org.kde.StatusNotifierWatcher")
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

    def build_topbar_label(self, data: dict) -> str:
        parts = []
        providers_raw = data.get("providers", {})
        fmt = self.cfg.get("topbar_format", "standard")

        for pid, pdata in providers_raw.items():
            p = deserialize_provider(pdata)
            if not p.ok:
                continue

            tag = "C" if pid == "claude" else ("AG" if pid == "antigravity" else ("CX" if pid == "codex" else ("GH" if pid == "copilot" else pid[:2].upper())))

            w5 = p.get_5h_window()
            wW = p.get_weekly_window()

            if fmt == "compact":
                s5 = f"{w5.remaining_pct}%" if w5 and w5.remaining_pct is not None else "--"
                sW = f"{wW.remaining_pct}%" if wW and wW.remaining_pct is not None else "--"
                if w5 and wW:
                    parts.append(f"{tag} {s5}·{sW}")
                elif wW:
                    parts.append(f"{tag} {sW}")
                elif w5:
                    parts.append(f"{tag} {s5}")
                elif p.windows:
                    first_pct = p.windows[0].remaining_pct
                    parts.append(f"{tag} {first_pct}%" if first_pct is not None else f"{tag} ok")
            else:
                sub_parts = []
                if w5 and w5.remaining_pct is not None:
                    sub_parts.append(f"5h {w5.remaining_pct}%")
                if wW and wW.remaining_pct is not None:
                    sub_parts.append(f"W {wW.remaining_pct}%")

                if sub_parts:
                    parts.append(f"{tag}: {' '.join(sub_parts)}")
                elif p.windows and p.windows[0].remaining_pct is not None:
                    parts.append(f"{tag}: {p.windows[0].remaining_pct}%")

        if not parts:
            return "AI Quota: active"
        return "   •   ".join(parts)

    def update_data(self, data: dict):
        label = self.build_topbar_label(data)
        self.item.set_label(label)
        self.menu.update_menu(data)

    def _on_timer(self):
        self.trigger_refresh()
        return GLib.SOURCE_CONTINUE

    def trigger_refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        curr = self.item.label.replace(" ⟳", "")
        self.item.set_label(f"{curr} ⟳")

        # 15s safety timeout to ensure "⟳" is never stuck
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
            curr = self.item.label.replace(" ⟳", "")
            self.item.set_label(curr)
        return GLib.SOURCE_REMOVE

    def _on_refresh_done(self, res):
        self._refreshing = False
        self.update_data(res)
        return GLib.SOURCE_REMOVE

    def _on_refresh_failed(self):
        self._refreshing = False
        curr = self.item.label.replace(" ⟳", "")
        self.item.set_label(curr)
        return GLib.SOURCE_REMOVE

    def quit(self):
        try:
            self.item.NewStatus("Passive")
        except Exception:
            pass
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
