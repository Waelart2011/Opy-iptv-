import threading
import time
import os
import sys

# شغّل Flask في الخلفية
def start_flask():
    from OPY_IPTV_V18_9_CLOUDFLARE import _run_web_mode
    _run_web_mode()

threading.Thread(target=start_flask, daemon=True).start()
time.sleep(2)

# افتح WebView على Flask
from android.webview import WebView
WebView.open("http://127.0.0.1:5000")
