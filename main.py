from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from android.permissions import request_permissions, Permission
import threading
import subprocess
import os
import sys

# أضف مسار البرنامج
sys.path.insert(0, os.path.dirname(__file__))


class OPYApp(App):
    def build(self):
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=10)

        self.status = Label(
            text='🎬 Opy IPTV V18.9\nجاري التشغيل...',
            font_size='18sp',
            halign='center'
        )
        self.layout.add_widget(self.status)

        self.url_label = Label(
            text='',
            font_size='14sp',
            halign='center',
            color=(0, 1, 0.5, 1)
        )
        self.layout.add_widget(self.url_label)

        self.open_btn = Button(
            text='📱 فتح في المتصفح',
            size_hint=(1, 0.2),
            background_color=(0.16, 0.5, 0.73, 1),
            disabled=True
        )
        self.open_btn.bind(on_press=self.open_browser)
        self.layout.add_widget(self.open_btn)

        self.cf_btn = Button(
            text='🌍 Cloudflare Tunnel',
            size_hint=(1, 0.2),
            background_color=(0.56, 0.27, 0.68, 1),
            disabled=True
        )
        self.cf_btn.bind(on_press=self.start_cloudflare)
        self.layout.add_widget(self.cf_btn)

        # شغّل Flask
        threading.Thread(target=self.start_flask, daemon=True).start()

        return self.layout

    def start_flask(self):
        try:
            from opy_server import start_server
            threading.Thread(target=start_server, daemon=True).start()
            import time; time.sleep(2)
            Clock.schedule_once(lambda dt: self.on_flask_ready(), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: self.on_error(str(e)), 0)

    def on_flask_ready(self):
        self.status.text = '✅ Opy IPTV V18.9\nجاهز للاستخدام'
        self.url_label.text = 'http://127.0.0.1:5000'
        self.open_btn.disabled = False
        self.cf_btn.disabled = False

    def on_error(self, msg):
        self.status.text = f'❌ خطأ:\n{msg}'

    def open_browser(self, *a):
        from android import mActivity
        from jnius import autoclass
        Intent = autoclass('android.content.Intent')
        Uri = autoclass('android.net.Uri')
        intent = Intent(Intent.ACTION_VIEW, Uri.parse('http://127.0.0.1:5000'))
        mActivity.startActivity(intent)

    def start_cloudflare(self, *a):
        self.cf_btn.disabled = True
        self.cf_btn.text = '⏳ جاري الاتصال...'
        threading.Thread(target=self._run_cf, daemon=True).start()

    def _run_cf(self):
        import re, urllib.request, platform
        cf = '/data/data/com.termux/files/usr/bin/cloudflared'
        if not os.path.isfile(cf):
            cf = os.path.expanduser('~/cloudflared')
            arch = platform.machine().lower()
            if 'aarch64' in arch or 'arm64' in arch:
                url = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64'
            else:
                url = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64'
            urllib.request.urlretrieve(url, cf)
            os.chmod(cf, 0o755)

        proc = subprocess.Popen(
            [cf, 'tunnel', '--url', 'http://localhost:5000'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            m = re.search(r'https://[\w\-]+\.trycloudflare\.com', line)
            if m:
                link = m.group()
                Clock.schedule_once(lambda dt, l=link: self.on_cf_ready(l), 0)
                break

    def on_cf_ready(self, link):
        self.cf_btn.text = '🌍 ' + link
        self.url_label.text = link


if __name__ == '__main__':
    OPYApp().run()
