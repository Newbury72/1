from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.clock import Clock
import threading
import subprocess
import os
import sys

from ai_state import load_config, save_config, record_training_event
from ai_core import AIModelDB, SimpleAIModel
from agent_core import AgentMemory


class HelperController(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 16
        self.spacing = 12
        self.config = load_config()
        self.proc = None
        self.thread = None
        self.overlay = None
        self.ai_db = AIModelDB(self.config.get('ai_db_path', 'ai_model.db'))
        self.ai_model = SimpleAIModel(self.ai_db)
        self.agent_memory = AgentMemory()

        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=12)
        header.add_widget(Label(text='Albion AI Helper', font_size=28, bold=True))
        header.add_widget(Button(text='AI Settings', size_hint=(None, None), size=(140, 44), on_press=self.show_settings))
        header.add_widget(Button(text='Reload config', size_hint=(None, None), size=(140, 44), on_press=self.load_settings))
        self.add_widget(header)

        control_panel = GridLayout(cols=1, spacing=10, size_hint_x=1)
        control_panel.add_widget(Label(text='Resource control', font_size=20, size_hint_y=None, height=40))
        self.resource_input = TextInput(text=self.config.get('resource', 'wood'), multiline=False, hint_text='Resource name')
        control_panel.add_widget(Label(text='Target resource'))
        control_panel.add_widget(self.resource_input)

        resource_buttons = GridLayout(cols=3, spacing=8, size_hint_y=None)
        resource_buttons.bind(minimum_height=resource_buttons.setter('height'))
        self.ore_button = Button(text='Ore / Руда', size_hint_y=None, height=42)
        self.stone_button = Button(text='Stone / Камень', size_hint_y=None, height=42)
        self.wood_button = Button(text='Wood / Дерево', size_hint_y=None, height=42)
        self.fiber_button = Button(text='Fiber / Хлопок', size_hint_y=None, height=42)
        self.hide_button = Button(text='Hide / Кожа', size_hint_y=None, height=42)
        resource_buttons.add_widget(self.ore_button)
        resource_buttons.add_widget(self.stone_button)
        resource_buttons.add_widget(self.wood_button)
        resource_buttons.add_widget(self.fiber_button)
        resource_buttons.add_widget(self.hide_button)
        control_panel.add_widget(resource_buttons)

        self.db_input = TextInput(text=self.config.get('db_path', 'assistant.db'), multiline=False, hint_text='Database path')
        self.remote_input = TextInput(text=self.config.get('remote_url', ''), multiline=False, hint_text='Remote URL')
        self.video_input = TextInput(text=self.config.get('video_path', ''), multiline=False, hint_text='Video path')
        self.ai_spinner = Spinner(text=self.config.get('ai_mode', 'local').capitalize(), values=['Local', 'Remote', 'Video'], size_hint_y=None, height=44)
        self.device_spinner = Spinner(text=self.config.get('device', 'poco_f5'), values=['poco_f5', 'desktop', 'custom'], size_hint_y=None, height=44)
        self.run_mode_spinner = Spinner(text=self.config.get('run_mode', 'no-root'), values=['no-root', 'adb', 'adb-wifi', 'video'], size_hint_y=None, height=44)
        self.loop_mode_spinner = Spinner(text='Loop', values=['Loop', 'One shot'], size_hint_y=None, height=44)
        self.adb_device_input = TextInput(text=self.config.get('adb_device', ''), multiline=False, hint_text='ADB device serial')
        self.adb_wifi_input = TextInput(text=self.config.get('adb_wifi', ''), multiline=False, hint_text='ADB WiFi host:port')

        control_panel.add_widget(Label(text='Database file'))
        control_panel.add_widget(self.db_input)
        control_panel.add_widget(Label(text='Remote training URL'))
        control_panel.add_widget(self.remote_input)
        control_panel.add_widget(Label(text='Video training path'))
        control_panel.add_widget(self.video_input)
        control_panel.add_widget(Label(text='AI mode'))
        control_panel.add_widget(self.ai_spinner)
        control_panel.add_widget(Label(text='Device preset'))
        control_panel.add_widget(self.device_spinner)
        control_panel.add_widget(Label(text='Execution mode'))
        control_panel.add_widget(self.run_mode_spinner)
        control_panel.add_widget(Label(text='ADB device serial'))
        control_panel.add_widget(self.adb_device_input)
        control_panel.add_widget(Label(text='ADB WiFi host'))
        control_panel.add_widget(self.adb_wifi_input)
        control_panel.add_widget(Label(text='Run mode'))
        control_panel.add_widget(self.loop_mode_spinner)

        control_buttons = GridLayout(cols=2, spacing=10, size_hint_y=None)
        control_buttons.bind(minimum_height=control_buttons.setter('height'))
        self.start_button = Button(text='Start helper', size_hint_y=None, height=48)
        self.stop_button = Button(text='Stop helper', size_hint_y=None, height=48)
        self.train_remote_button = Button(text='Train remote', size_hint_y=None, height=48)
        self.train_video_button = Button(text='Train video', size_hint_y=None, height=48)
        self.clear_log_button = Button(text='Clear log', size_hint_y=None, height=48)
        control_buttons.add_widget(self.start_button)
        control_buttons.add_widget(self.stop_button)
        control_buttons.add_widget(self.train_remote_button)
        control_buttons.add_widget(self.train_video_button)
        control_buttons.add_widget(self.clear_log_button)
        control_panel.add_widget(control_buttons)

        data_panel = GridLayout(cols=1, spacing=10, size_hint_x=1)
        data_panel.add_widget(Label(text='AI data and storage', font_size=20, size_hint_y=None, height=40))
        self.ai_db_input = TextInput(text=self.config.get('ai_db_path', 'ai_model.db'), multiline=False, hint_text='AI model DB path')
        self.memory_input = TextInput(text=self.config.get('memory_path', 'ai_memory_backup.db'), multiline=False, hint_text='AI memory file path')
        self.memory_json_input = TextInput(text=self.config.get('memory_json_path', 'ai_memory_export.json'), multiline=False, hint_text='AI memory JSON path')

        data_panel.add_widget(Label(text='AI model DB path'))
        data_panel.add_widget(self.ai_db_input)
        data_panel.add_widget(Label(text='AI memory file'))
        data_panel.add_widget(self.memory_input)
        data_panel.add_widget(Label(text='AI memory JSON'))
        data_panel.add_widget(self.memory_json_input)

        data_buttons = GridLayout(cols=2, spacing=10, size_hint_y=None)
        data_buttons.bind(minimum_height=data_buttons.setter('height'))
        self.save_button = Button(text='Save settings', size_hint_y=None, height=48)
        self.backup_button = Button(text='Backup AI memory', size_hint_y=None, height=48)
        self.restore_button = Button(text='Restore AI memory', size_hint_y=None, height=48)
        self.export_json_button = Button(text='Export AI memory', size_hint_y=None, height=48)
        self.import_json_button = Button(text='Import AI memory', size_hint_y=None, height=48)

        data_buttons.add_widget(self.save_button)
        data_buttons.add_widget(self.backup_button)
        data_buttons.add_widget(self.restore_button)
        data_buttons.add_widget(self.export_json_button)
        data_buttons.add_widget(self.import_json_button)
        data_panel.add_widget(data_buttons)

        self.start_button.bind(on_press=self.start_helper)
        self.stop_button.bind(on_press=self.stop_helper)
        self.save_button.bind(on_press=self.save_settings)
        self.train_remote_button.bind(on_press=self.train_remote)
        self.train_video_button.bind(on_press=self.train_video)
        self.backup_button.bind(on_press=self.backup_memory)
        self.restore_button.bind(on_press=self.restore_memory)
        self.export_json_button.bind(on_press=self.export_memory_json)
        self.import_json_button.bind(on_press=self.import_memory_json)
        self.clear_log_button.bind(on_press=self.clear_log)
        self.ore_button.bind(on_press=lambda inst: self.select_resource('ore'))
        self.stone_button.bind(on_press=lambda inst: self.select_resource('stone'))
        self.wood_button.bind(on_press=lambda inst: self.select_resource('wood'))
        self.fiber_button.bind(on_press=lambda inst: self.select_resource('fiber'))
        self.hide_button.bind(on_press=lambda inst: self.select_resource('hide'))

        info_panel = BoxLayout(orientation='vertical', spacing=10)
        info_panel.add_widget(Label(text='AI memory overview', font_size=20, size_hint_y=None, height=40))
        self.summary_view = TextInput(text='', readonly=True, background_color=(0.96, 0.96, 0.96, 1), size_hint_y=0.4)
        info_panel.add_widget(self.summary_view)
        info_panel.add_widget(Label(text='Recent AI activity', size_hint_y=None, height=28))
        self.activity_view = TextInput(text='', readonly=True, background_color=(0.96, 0.96, 0.96, 1), size_hint_y=0.45)
        info_panel.add_widget(self.activity_view)
        self.refresh_stats_button = Button(text='Refresh AI status', size_hint_y=None, height=44)
        self.refresh_stats_button.bind(on_press=self.refresh_summary)
        info_panel.add_widget(self.refresh_stats_button)

        log_panel = BoxLayout(orientation='vertical', spacing=10)
        log_panel.add_widget(Label(text='Live status & log', font_size=20, size_hint_y=None, height=40))
        self.status = Label(text='Status: idle', font_size=16, size_hint_y=None, height=40)
        self.log_view = TextInput(text='Welcome to Albion AI Helper\n', readonly=True, background_color=(0.96, 0.96, 0.96, 1), size_hint_y=1)
        log_panel.add_widget(self.status)
        log_panel.add_widget(self.log_view)

        tabs = TabbedPanel(do_default_tab=False, tab_pos='top_mid')
        control_tab = TabbedPanelItem(text='Control')
        control_tab.add_widget(control_panel)
        tabs.add_widget(control_tab)

        data_tab = TabbedPanelItem(text='Data')
        data_tab.add_widget(data_panel)
        tabs.add_widget(data_tab)

        status_tab = TabbedPanelItem(text='AI status')
        status_tab.add_widget(info_panel)
        tabs.add_widget(status_tab)

        logs_tab = TabbedPanelItem(text='Logs')
        logs_tab.add_widget(log_panel)
        tabs.add_widget(logs_tab)

        self.add_widget(tabs)
        self.refresh_summary(None)

    def start_helper(self, instance):
        if self.proc and self.proc.poll() is None:
            self._append_log('Helper already running')
            return

        self.save_settings(None)
        resource = self.resource_input.text.strip() or 'wood'
        db_path = self.db_input.text.strip() or 'assistant.db'
        device = self.device_spinner.text
        run_mode = self.run_mode_spinner.text
        cmd = [sys.executable, 'app.py', '--resource', resource, '--db', db_path, '--device', device, '--mode', run_mode]
        if self.loop_mode_spinner.text == 'One shot':
            cmd.append('--once')

        self._append_log(f'Starting helper for {resource} using {run_mode} mode')
        self.status.text = 'Status: starting'
        if run_mode == 'video':
            video_path = self.video_input.text.strip()
            if not video_path:
                self._append_log('Video path is required for video mode')
                self.status.text = 'Status: video path missing'
                return
            cmd += ['--video', video_path]
        if run_mode == 'adb':
            adb_device = self.adb_device_input.text.strip()
            if adb_device:
                cmd += ['--adb-device', adb_device]
        if run_mode == 'adb-wifi':
            adb_wifi = self.adb_wifi_input.text.strip()
            if not adb_wifi:
                self._append_log('ADB WiFi host is required for adb-wifi mode')
                self.status.text = 'Status: adb-wifi host missing'
                return
            cmd += ['--adb-wifi', adb_wifi]
        self.proc = subprocess.Popen(cmd, cwd=os.getcwd(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.thread = threading.Thread(target=self._read_output, daemon=True)
        self.thread.start()
        self._show_overlay('ON')

    def stop_helper(self, instance):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self._append_log('Helper stopped')
            self.status.text = 'Status: stopped'
        else:
            self._append_log('Nothing is running')
            self.status.text = 'Status: idle'
        self._show_overlay('OFF')

    def save_settings(self, instance):
        config = {
            'resource': self.resource_input.text.strip() or 'wood',
            'db_path': self.db_input.text.strip() or 'assistant.db',
            'remote_url': self.remote_input.text.strip(),
            'video_path': self.video_input.text.strip(),
            'ai_db_path': self.ai_db_input.text.strip() or 'ai_model.db',
            'memory_path': self.memory_input.text.strip() or 'ai_memory_backup.db',
            'memory_json_path': self.memory_json_input.text.strip() or 'ai_memory_export.json',
            'ai_mode': self.ai_spinner.text.lower(),
            'device': self.device_spinner.text,
            'run_mode': self.run_mode_spinner.text,
            'adb_device': self.adb_device_input.text.strip(),
            'adb_wifi': self.adb_wifi_input.text.strip(),
        }
        save_config(config)
        self._refresh_ai_db()
        self.refresh_summary(None)
        self._append_log('Settings saved')
        self.status.text = 'Status: settings saved'

    def load_settings(self, instance=None):
        self.config = load_config()
        self.resource_input.text = self.config.get('resource', 'wood')
        self.db_input.text = self.config.get('db_path', 'assistant.db')
        self.remote_input.text = self.config.get('remote_url', '')
        self.video_input.text = self.config.get('video_path', '')
        self.ai_db_input.text = self.config.get('ai_db_path', 'ai_model.db')
        self.memory_input.text = self.config.get('memory_path', 'ai_memory_backup.db')
        self.memory_json_input.text = self.config.get('memory_json_path', 'ai_memory_export.json')
        self.ai_spinner.text = self.config.get('ai_mode', 'local').capitalize()
        self.device_spinner.text = self.config.get('device', 'poco_f5')
        self.run_mode_spinner.text = self.config.get('run_mode', 'no-root')
        self.adb_device_input.text = self.config.get('adb_device', '')
        self.adb_wifi_input.text = self.config.get('adb_wifi', '')
        self._refresh_ai_db()
        self.refresh_summary(None)
        self._append_log('Settings loaded')
        self.status.text = 'Status: settings loaded'

    def show_settings(self, instance):
        popup_content = BoxLayout(orientation='vertical', spacing=12, padding=12)
        popup_content.add_widget(Label(text='AI Settings', font_size=20, size_hint_y=None, height=36))
        popup_content.add_widget(Label(text='- Select the target resource\n- Choose DB and training input\n- Use remote or video training when needed'))
        close_button = Button(text='Close', size_hint_y=None, height=44)
        popup_content.add_widget(close_button)
        popup = Popup(title='AI settings', content=popup_content, size_hint=(0.8, 0.5))
        close_button.bind(on_press=popup.dismiss)
        popup.open()

    def train_remote(self, instance):
        resource = self.resource_input.text.strip() or 'wood'
        remote_url = self.remote_input.text.strip()
        if not remote_url:
            self._append_log('Remote URL is required for remote training')
            self.status.text = 'Status: training failed'
            return
        config = load_config()
        record_training_event(config, 'remote', remote_url, resource, 'Remote training requested')
        try:
            self.ai_model.train_from_remote_url(remote_url, resource)
            self._append_log('Remote AI training completed')
            self.status.text = 'Status: remote training done'
        except Exception as exc:
            self._append_log(f'Remote training error: {exc}')
            self.status.text = 'Status: training failed'

    def train_video(self, instance):
        resource = self.resource_input.text.strip() or 'wood'
        video_path = self.video_input.text.strip()
        if not video_path:
            self._append_log('Video path is required for video training')
            self.status.text = 'Status: training failed'
            return
        config = load_config()
        record_training_event(config, 'video', video_path, resource, 'Video training requested')
        try:
            self.ai_model.train_from_video(video_path, resource)
            self._append_log('Video AI training completed')
            self.status.text = 'Status: video training done'
            self.refresh_summary(None)
        except Exception as exc:
            self._append_log(f'Video training error: {exc}')
            self.status.text = 'Status: training failed'

    def backup_memory(self, instance):
        target = self.memory_input.text.strip() or 'ai_memory_backup.db'
        try:
            self.ai_db.backup(target)
            self._append_log(f'AI memory backed up to {target}')
            self.status.text = 'Status: memory backed up'
        except Exception as exc:
            self._append_log(f'Backup error: {exc}')
            self.status.text = 'Status: backup failed'

    def restore_memory(self, instance):
        source = self.memory_input.text.strip() or 'ai_memory_backup.db'
        try:
            self.ai_db.restore(source)
            self.ai_model = SimpleAIModel(self.ai_db)
            self._append_log(f'AI memory restored from {source}')
            self.status.text = 'Status: memory restored'
            self.refresh_summary(None)
        except Exception as exc:
            self._append_log(f'Restore error: {exc}')
            self.status.text = 'Status: restore failed'

    def export_memory_json(self, instance):
        target = self.memory_json_input.text.strip() or 'ai_memory_export.json'
        try:
            self.ai_db.export_json(target)
            self._append_log(f'AI memory exported to {target}')
            self.status.text = 'Status: memory exported'
        except Exception as exc:
            self._append_log(f'Export error: {exc}')
            self.status.text = 'Status: export failed'

    def import_memory_json(self, instance):
        source = self.memory_json_input.text.strip() or 'ai_memory_export.json'
        try:
            self.ai_db.import_json(source)
            self.ai_model = SimpleAIModel(self.ai_db)
            self._append_log(f'AI memory imported from {source}')
            self.status.text = 'Status: memory imported'
            self.refresh_summary(None)
        except Exception as exc:
            self._append_log(f'Import error: {exc}')
            self.status.text = 'Status: import failed'

    def refresh_summary(self, instance=None):
        summary = self.ai_db.get_summary()
        weights = self.ai_db.get_weights()
        activity = self.ai_db.get_activity(10)
        decisions = self.agent_memory.get_recent_decisions(10)

        summary_lines = ["Weights:"]
        for weight in weights:
            summary_lines.append(f"{weight['resource_name']}: {weight['score']:.2f} ({weight['updated_at']})")
        summary_lines.append("")
        summary_lines.append("Sample counts:")
        for resource, stats in summary.items():
            summary_lines.append(f"{resource}: {stats['count']} samples, {stats['successes']} successes")
        self.summary_view.text = "\n".join(summary_lines)

        activity_lines = ["Recent AI activity:"]
        for event in activity:
            activity_lines.append(f"[{event['created_at']}] {event['event_type']} {event['resource_name'] or ''} {event['event_source'] or ''} {event['detail'] or ''}")
        activity_lines.append("")
        activity_lines.append("Recent decisions:")
        for decision in decisions:
            activity_lines.append(f"[{decision['created_at']}] {decision['resource_name']} score={decision['score']:.2f} reason={decision['reason']}")
        self.activity_view.text = "\n".join(activity_lines)
        self._append_log('AI status updated')

    def clear_log(self, instance):
        self.log_view.text = ''
        self._append_log('Log cleared')

    def _refresh_ai_db(self):
        path = self.ai_db_input.text.strip() or 'ai_model.db'
        try:
            self.ai_db = AIModelDB(path)
            self.ai_model = SimpleAIModel(self.ai_db)
        except Exception as exc:
            self._append_log(f'AI DB refresh error: {exc}')
            self.status.text = 'Status: AI DB load failed'

    def select_resource(self, resource_name):
        self.resource_input.text = resource_name
        self._append_log(f'Selected resource: {resource_name}')
        self.status.text = f'Status: selected {resource_name}'

    def _read_output(self):
        assert self.proc is not None
        for line in self.proc.stdout:  # type: ignore[attr-defined]
            Clock.schedule_once(lambda dt, line=line: self._append_log(line.rstrip()))
        self.proc.wait()
        Clock.schedule_once(lambda dt: self._append_log('Helper finished'))

    def _append_log(self, text):
        self.log_view.text += f'{text}\n'
        self.log_view.cursor = (0, len(self.log_view.text.splitlines()))
        self.status.text = f'Status: {text}'

    def _show_overlay(self, state):
        if self.overlay is None:
            from kivy.uix.floatlayout import FloatLayout
            from kivy.graphics import Color, Rectangle
            from kivy.core.window import Window
            self.overlay = FloatLayout(size_hint=(None, None), size=(100, 100), pos=(20, 20))
            with self.overlay.canvas.before:
                Color(0, 0, 0, 0.7)
                self.overlay_bg = Rectangle(size=self.overlay.size, pos=self.overlay.pos)
            self.overlay.add_widget(Label(text='AI', font_size=20, color=(1, 1, 1, 1), pos_hint={'center_x': 0.5, 'center_y': 0.5}))
            Window.add_widget(self.overlay)
        self.overlay.children[0].text = f'AI {state}'


class AlbionAIApp(App):
    def build(self):
        return HelperController()


if __name__ == '__main__':
    AlbionAIApp().run()
