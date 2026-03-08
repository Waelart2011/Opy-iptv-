# هذا الملف يشغّل Flask server من داخل APK
import sys
import os

def start_server():
    """تشغيل Flask في الخلفية"""
    # استيراد الدوال من الملف الرئيسي
    try:
        from OPY_IPTV_V18_9_CLOUDFLARE import _run_web_mode
        _run_web_mode()
    except Exception as e:
        print(f"Server error: {e}")
