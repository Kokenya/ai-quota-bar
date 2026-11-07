import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const CACHE_PATH = GLib.build_filenamev([GLib.get_home_dir(), '.cache', 'ai-quota-bar', 'status.json']);
const CLI_PATH = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'ai-usage']);
const UPDATE_INTERVAL_SECONDS = 120;

const AIQuotaIndicator = GObject.registerClass(
class AIQuotaIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'AI Quota Bar');

        this._box = new St.BoxLayout({
            style_class: 'panel-status-indicators-box ai-quota-box',
            y_align: Clutter.ActorAlign.CENTER,
        });

        this._icon = new St.Icon({
            icon_name: 'utilities-system-monitor-symbolic',
            style_class: 'system-status-icon',
        });
        this._box.add_child(this._icon);

        this._label = new St.Label({
            text: 'AI Quota...',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'ai-quota-label',
        });
        this._box.add_child(this._label);

        this.add_child(this._box);
        this._loadFromCache();
    }

    _loadFromCache() {
        if (!GLib.file_test(CACHE_PATH, GLib.FileTest.EXISTS)) return;
        try {
            let [ok, contents] = GLib.file_get_contents(CACHE_PATH);
            if (ok) {
                let decoder = new TextDecoder('utf-8');
                let data = JSON.parse(decoder.decode(contents));
                this._render(data);
            }
        } catch (e) {
            log(`[AIQuotaBar] Cache read error: ${e}`);
        }
    }

    _render(data) {
        if (!data || !data.providers) return;
        let parts = [];
        for (let [pid, p] of Object.entries(data.providers)) {
            if (!p.ok) continue;
            let tag = pid === 'claude' ? 'C' : (pid === 'antigravity' ? 'AG' : (pid === 'codex' ? 'CX' : pid.slice(0, 2).toUpperCase()));
            let w5 = (p.windows || []).find(w => w.window_type === '5h' || (w.name && w.name.includes('5h')));
            let wW = (p.windows || []).find(w => w.window_type === 'weekly' || (w.name && w.name.toLowerCase().includes('week')));
            let sub = [];
            if (w5 && w5.remaining_pct !== null && w5.remaining_pct !== undefined) sub.push(`5h ${w5.remaining_pct}%`);
            if (wW && wW.remaining_pct !== null && wW.remaining_pct !== undefined) sub.push(`W ${wW.remaining_pct}%`);
            if (sub.length > 0) {
                parts.push(`${tag}: ${sub.join(' ')}`);
            } else if (p.windows && p.windows.length > 0 && p.windows[0].remaining_pct !== null) {
                parts.push(`${tag}: ${p.windows[0].remaining_pct}%`);
            }
        }
        if (parts.length > 0) {
            this._label.set_text(parts.join('   •   '));
        }
    }

    refresh() {
        try {
            let proc = new Gio.Subprocess({
                argv: [CLI_PATH, '--refresh', '--json'],
                flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
            });
            proc.init(null);
            proc.communicate_utf8_async(null, null, (obj, res) => {
                try {
                    let [ok, stdout] = obj.communicate_utf8_finish(res);
                    if (ok && stdout) {
                        let data = JSON.parse(stdout);
                        this._render(data);
                    }
                } catch (err) {
                    this._loadFromCache();
                }
            });
        } catch (e) {
            this._loadFromCache();
        }
    }
});

export default class AIQuotaBarExtension extends Extension {
    enable() {
        this._indicator = new AIQuotaIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator, 1, 'right');
        this._indicator.refresh();

        this._timerId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT,
            UPDATE_INTERVAL_SECONDS,
            () => {
                this._indicator?.refresh();
                return GLib.SOURCE_CONTINUE;
            }
        );
    }

    disable() {
        if (this._timerId) {
            GLib.source_remove(this._timerId);
            this._timerId = null;
        }
        this._indicator?.destroy();
        this._indicator = null;
    }
}
