# -*- coding: utf-8 -*-
# ==============================================================
#
#    ██████╗ ██████╗ ██╗   ██╗    ██╗██████╗ ████████╗██╗   ██╗
#   ██╔═══██╗██╔══██╗╚██╗ ██╔╝    ██║██╔══██╗╚══██╔══╝██║   ██║
#   ██║   ██║██████╔╝ ╚████╔╝     ██║██████╔╝   ██║   ██║   ██║
#   ██║   ██║██╔═══╝   ╚██╔╝      ██║██╔═══╝    ██║   ╚██╗ ██╔╝
#   ╚██████╔╝██║        ██║       ██║██║        ██║    ╚████╔╝
#    ╚═════╝ ╚═╝        ╚═╝       ╚═╝╚═╝        ╚═╝     ╚═══╝
#
#   Opy IPTV V18.9 — المدير الشامل لقوائم IPTV
#   الإصدار: 2.0
#   المطور: Wael
#
#   الميزات:
#   ✅ إدارة ملفات M3U (تحميل، تعديل، حذف، إضافة، بحث)
#   ✅ اتصال مباشر بخوادم Xtream API
#   ✅ جلب القنوات الحية مع كل معلوماتها
#   ✅ جلب الأفلام مع التصنيفات والملصقات
#   ✅ جلب المسلسلات مع أرقام المواسم والحلقات
#   ✅ فحص ذكي يتعرف على نوع البث ويتكيف معه
#   ✅ تقرير مفصل بعد كل فحص
#   ✅ حفظ كل قسم في ملف M3U منفصل
# ==============================================================

# ==============================================================
# المكتبات
# ==============================================================

# tkinter — اختياري، يُستورَد فقط إذا كان متاحاً (لا يعمل على Termux/Android)
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk, Canvas
    _HAS_TK = True
except ImportError:
    _HAS_TK = False

import re
# re = Regular Expressions = أداة البحث بالأنماط النصية
# نستخدمها لتحليل أسطر #EXTINF واستخراج القيم منها

import threading
# threading = تعدد الخيوط لتشغيل العمليات الثقيلة في الخلفية
# بدونه: الفحص يجمّد الواجهة حتى ينتهي

import requests
# requests = مكتبة HTTP للتواصل مع الخوادم والـ APIs
# pip install requests

from concurrent.futures import ThreadPoolExecutor, as_completed
# ThreadPoolExecutor = مجمع خيوط متوازية
# as_completed = يُرجع النتائج فور انتهائها لا بترتيب البداية
# هذا هو سر تحديث progress bar بسلاسة:
# بدل الانتظار حتى تنتهي القناة رقم 0 ليبدأ العرض،
# نعرض نتيجة أي قناة تنتهي أولاً فوراً

import urllib3
# urllib3 = مكتبة HTTP داخلية
# نستوردها لتعطيل تحذيرات SSL فقط

import itertools
# itertools = أدوات التكرار
# cycle() = دوران لا نهائي على قائمة (لألوان التوهج)

import os
# os = أدوات نظام التشغيل
# os.path = للتعامل مع مسارات الملفات

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# إيقاف تحذيرات "Unverified HTTPS" المزعجة
# كثير من خوادم IPTV شهاداتها SSL غير موثوقة

# ==============================================================
# المتغيرات العامة للمحرر
# ==============================================================

channels         = []
# قائمة كل القنوات المحملة في المحرر
# كل عنصر = dict: {extinf, name, category, url}

channels_status  = []
# حالة كل قناة: None=لم تُفحص, True=شغالة, False=ميتة
# موازية تماماً لـ channels (نفس الطول والترتيب)

filtered_indices = []
# خريطة: filtered_indices[listbox_idx] = channels_idx الحقيقي
# تُعاد بناؤها في كل refresh_listbox
# تحل مشكلة الفهارس الخاطئة عند الفلترة

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Safari/537.36/okhttp/4.12.0/stagefright/1.2 (Linux;Android 13)"
)

# قائمة User-Agents للمحاولات المتعددة
# بعض الخوادم تقبل نوعاً معيناً وترفض الباقي
_USER_AGENTS = [
    # مشغل IPTV Android (الأقوى — معظم الخوادم تتعرف عليه)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Safari/537.36/okhttp/4.12.0/stagefright/1.2 (Linux;Android 13)",
    # VLC Player
    "VLC/3.0.18 LibVLC/3.0.18",
    # Kodi
    "Kodi/20.0 (X11; Linux x86_64) App_Bitness/64 Version/20.0",
    # okhttp (مكتبة Android الشائعة)
    "okhttp/4.12.0",
]
# User-Agent = هوية البرنامج في طلبات HTTP
# نجعله يشبه Chrome لتجاوز حماية بعض الخوادم

# ==============================================================
# دوال تحليل ملفات M3U
# ==============================================================

def load_m3u(path):
    """تحميل ملف M3U — iteration بدون تحميل كامل في الذاكرة"""
    global channels, channels_status
    channels.clear()
    channels_status.clear()
    if not path:
        messagebox.showerror("خطأ", "اختر ملف M3U أولاً")
        return
    try:
        extinf_line = None
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:                          # iteration سطر بسطر
                line = raw.strip()
                if not line: continue
                if line.startswith("#EXTINF"):
                    extinf_line = line
                elif extinf_line and not line.startswith("#"):
                    name = extinf_line.split(",")[-1].strip()
                    m    = re.search(r'group-title="([^"]+)"', extinf_line)
                    if not m: m = re.search(r'tvg-category="([^"]+)"', extinf_line)
                    cat  = m.group(1) if m else ""
                    ml   = re.search(r'tvg-logo="([^"]+)"', extinf_line)
                    logo = ml.group(1) if ml else ""
                    channels.append({"extinf": extinf_line, "name": name, "category": cat, "url": line, "logo": logo})
                    channels_status.append(None)
                    extinf_line = None
    except Exception as e:
        messagebox.showerror("خطأ", f"تعذر فتح الملف:\n{e}")
        return
    refresh_listbox()
    messagebox.showinfo("تم", f"✅ تم تحميل {len(channels)} قناة")

def save_m3u(path):
    """حفظ channels دفعة واحدة — أسرع من الكتابة المتكررة"""
    if not path:
        messagebox.showerror("خطأ", "اختر مسار الحفظ أولاً")
        return
    try:
        lines = ["#EXTM3U"]
        for ch in channels:
            lines.append(ch["extinf"])
            lines.append(ch["url"])
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        messagebox.showinfo("تم", f"✅ تم حفظ {len(channels)} قناة")
    except Exception as e:
        messagebox.showerror("خطأ", f"فشل الحفظ:\n{e}")

# ==============================================================
# إدارة القائمة المرئية + خريطة الفهارس
# ==============================================================

def refresh_listbox(filter_text=""):
    """إعادة رسم الـ Listbox مع بناء خريطة filtered_indices"""
    global filtered_indices
    filtered_indices = []
    listbox.delete(0, tk.END)

    for i, ch in enumerate(channels):
        if filter_text.lower() in ch["name"].lower() or filter_text.lower() in ch["category"].lower():
            filtered_indices.append(i)
            # نبني نص العرض مع حالة الفحص
            txt = f'{ch["name"]}  |  {ch["category"]}'
            if channels_status[i] is True:
                txt += "  ✅"
            elif channels_status[i] is False:
                txt += "  ❌"
            listbox.insert(tk.END, txt)

    lbl_count.config(text=f"إجمالي القنوات: {len(channels)}  |  معروض: {len(filtered_indices)}")
    update_sel_count()

def get_real_index(lb_idx):
    """تحويل فهرس Listbox ← فهرس channels الحقيقي"""
    if lb_idx < len(filtered_indices):
        return filtered_indices[lb_idx]
    return None

def update_sel_count():
    lbl_sel.config(text=f"محدد: {len(listbox.curselection())}")

# ==============================================================
# تفاعل المستخدم مع القائمة
# ==============================================================

def on_select(event):
    sel = listbox.curselection()
    if not sel:
        return
    real = get_real_index(sel[0])
    if real is None:
        return
    ch = channels[real]
    entry_name.delete(0, tk.END); entry_name.insert(0, ch["name"])
    entry_cat.delete(0, tk.END);  entry_cat.insert(0, ch["category"])
    entry_url.delete(0, tk.END);  entry_url.insert(0, ch["url"])
    update_sel_count()

def save_edit():
    sel = listbox.curselection()
    if not sel:
        messagebox.showwarning("تنبيه", "اختر قناة أولاً")
        return
    real = get_real_index(sel[0])
    if real is None: return
    ch = channels[real]
    ch["name"]     = entry_name.get().strip()
    ch["category"] = entry_cat.get().strip()
    ch["url"]      = entry_url.get().strip()
    ext = ch["extinf"]
    if 'tvg-category="' in ext:
        ext = re.sub(r'tvg-category="[^"]*"', f'tvg-category="{ch["category"]}"', ext)
    elif 'group-title="' in ext:
        ext = re.sub(r'group-title="[^"]*"', f'group-title="{ch["category"]}"', ext)
    parts = ext.split(","); parts[-1] = ch["name"]
    ch["extinf"] = ",".join(parts)
    refresh_listbox(entry_search.get())

def add_channel():
    name = entry_name.get().strip()
    url  = entry_url.get().strip()
    cat  = entry_cat.get().strip()
    if not name or not url:
        messagebox.showwarning("تنبيه", "الاسم والرابط مطلوبان")
        return
    channels.append({"extinf": f'#EXTINF:-1 tvg-category="{cat}",{name}', "name": name, "category": cat, "url": url})
    channels_status.append(None)
    refresh_listbox(entry_search.get())

def delete_channels():
    sel = listbox.curselection()
    if not sel:
        messagebox.showwarning("تنبيه", "اختر قناة أو أكثر")
        return
    for idx in sorted([get_real_index(i) for i in sel if get_real_index(i) is not None], reverse=True):
        channels.pop(idx); channels_status.pop(idx)
    refresh_listbox(entry_search.get())

def toggle_multi():
    if listbox["selectmode"] == tk.BROWSE:
        listbox.config(selectmode=tk.MULTIPLE)
        btn_multi.config(text="⬛ إيقاف متعدد")
    else:
        listbox.config(selectmode=tk.BROWSE)
        btn_multi.config(text="☑ اختيار متعدد")

def replace_name():
    old = entry_old.get(); new_t = entry_new.get()
    if not old: return
    sel = listbox.curselection()
    targets = sel if sel else range(len(filtered_indices))
    changed = 0
    for lb in targets:
        real = get_real_index(lb)
        if real is None: continue
        old_name = channels[real]["name"]
        channels[real]["name"] = old_name.replace(old, new_t)
        if channels[real]["name"] != old_name:
            parts = channels[real]["extinf"].split(",")
            parts[-1] = channels[real]["name"]
            channels[real]["extinf"] = ",".join(parts)
            changed += 1
    refresh_listbox(entry_search.get())
    messagebox.showinfo("تم", f"تم تعديل {changed} قناة")

def select_offline():
    listbox.selection_clear(0, tk.END)
    for lb, real in enumerate(filtered_indices):
        if channels_status[real] is False:
            listbox.selection_set(lb)
    update_sel_count()

def select_online():
    listbox.selection_clear(0, tk.END)
    for lb, real in enumerate(filtered_indices):
        if channels_status[real] is True:
            listbox.selection_set(lb)
    update_sel_count()

# ==============================================================
# الفحص الذكي المتكيف
# ==============================================================

def detect_stream_type(url):
    u = url.lower()
    if "/live/" in u and (u.endswith(".ts") or u.endswith(".m3u8")): return "xtream_live"
    if "/movie/" in u:    return "xtream_movie"
    if "/series/" in u:   return "xtream_series"
    if u.endswith(".m3u8") or "m3u8" in u: return "hls"
    if u.endswith(".mpd") or "/dash/" in u: return "dash"
    if u.startswith("rtmp://") or u.startswith("rtmps://"): return "rtmp"
    if u.startswith("udp://") or u.startswith("rtp://"): return "udp"
    if "youtube.com" in u or "youtu.be" in u: return "youtube"
    return "http"

# الـ headers التي يرسلها مشغل IPTV حقيقي
_PLAYER_HEADERS = {
    "User-Agent":       USER_AGENT,
    "Accept":           "*/*",
    "Accept-Language":  "en-US,en;q=0.9",
    "Connection":       "keep-alive",
    "Range":            "bytes=0-1024",  # نجلب أول كيلوبايت فقط — أسرع بكثير
}

# عدد الخيوط الديناميكي حسب أنوية المعالج
_MAX_WORKERS = min(200, (os.cpu_count() or 4) * 40)

# cache للروابط المفحوصة — يمنع إعادة الفحص لنفس الرابط
_check_cache = {}

# Session لكل خيط منفصل — thread-safe ويعيد استخدام الاتصال
import threading as _th
_session_local = _th.local()

def _get_session():
    """يُرجع Session خاص بالخيط الحالي مع Connection Pool"""
    if not hasattr(_session_local, "session"):
        from requests.adapters import HTTPAdapter
        s = requests.Session()
        s.verify = False
        s.headers.update(_PLAYER_HEADERS)
        # Connection Pool — يعيد استخدام الاتصالات بدل فتح جديد لكل طلب
        adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100)
        s.mount("http://",  adapter)
        s.mount("https://", adapter)
        _session_local.session = s
    return _session_local.session

def _check_http(url):
    """فحص HTTP — Session + Cache + Range + redirect"""
    if url in _check_cache: return _check_cache[url]
    for ua in _USER_AGENTS:
        try:
            sess = _get_session()
            r = sess.get(url,
                headers={"User-Agent": ua, "Range": "bytes=0-1024"},
                timeout=4, stream=True, verify=False,
                allow_redirects=True)
            if r.status_code < 400:
                _check_cache[url] = True;  return True
            if r.status_code in (401, 403): continue
            _check_cache[url] = False; return False
        except: continue
    _check_cache[url] = False
    return False

def _check_xtream_live(url):
    """فحص Xtream — GET بسيط يتبع redirect"""
    if url in _check_cache: return _check_cache[url]
    for ua in _USER_AGENTS:
        try:
            sess = _get_session()
            r = sess.get(url,
                headers={"User-Agent": ua, "Accept": "*/*", "Connection": "keep-alive"},
                timeout=6, stream=True, verify=False,
                allow_redirects=True)
            if r.status_code < 400:
                _check_cache[url] = True; return True
            if r.status_code in (401, 403): continue
            _check_cache[url] = False; return False
        except: continue
    _check_cache[url] = False
    return False

def _check_hls(url):
    """فحص HLS — Cache + 250 حرف فقط"""
    if url in _check_cache: return _check_cache[url]
    for ua in _USER_AGENTS:
        try:
            sess = _get_session()
            r = sess.get(url,
                headers={"User-Agent": ua},
                timeout=4, verify=False, allow_redirects=True)
            if r.status_code >= 400:
                if r.status_code in (401, 403): continue
                _check_cache[url] = False; return False
            content = r.text[:250]   # 250 يكفي للتحقق من #EXTM3U
            if "#EXTM3U" in content or "#EXT-X-" in content:
                _check_cache[url] = True;  return True
            if "<html" in content.lower() and "404" in content:
                _check_cache[url] = False; return False
            if r.status_code in (200, 206):
                _check_cache[url] = True;  return True
        except: continue
    _check_cache[url] = False
    return False

def _extract_xtream_key(url):
    """استخراج مفتاح الخادم من رابط Xtream — domain/user/pass"""
    try:
        # مثال: http://server:8789/live/user/pass/13973.ts
        parts = url.split("/")
        # parts = ['http:', '', 'server:8789', 'live', 'user', 'pass', '13973.ts']
        if len(parts) >= 6:
            return f"{parts[2]}/{parts[4]}/{parts[5]}"  # domain/user/pass
    except: pass
    return url

def smart_test_channel(idx_url):
    """الفحص الذكي — يختار الاستراتيجية المناسبة لكل نوع"""
    idx, url = idx_url
    stype = detect_stream_type(url)
    if stype in ("rtmp", "udp"):                              return idx, None,                    stype
    if stype == "xtream_live":                                return idx, _check_xtream_live(url), stype
    if stype == "hls":                                        return idx, _check_hls(url),         stype
    if stype in ("xtream_movie", "xtream_series", "http"):    return idx, _check_http(url),        stype
    return idx, _check_http(url), stype

# نتائج فحص الخوادم — مشترك بين كل الخيوط
_server_results = {}
_server_lock    = _th.Lock()
_server_events  = {}  # event لكل خادم — يُطلق عند اكتمال الفحص

def smart_test_channel_grouped(idx_url):
    """فحص ذكي — يفحص كل خادم مرة واحدة فقط"""
    idx, url = idx_url
    stype = detect_stream_type(url)

    if stype in ("rtmp", "udp"):
        return idx, None, stype

    if stype == "xtream_live":
        key = _extract_xtream_key(url)

        with _server_lock:
            if key in _server_results:
                # نتيجة جاهزة
                return idx, _server_results[key], stype
            if key in _server_events:
                # خيط آخر يفحص — احصل على الـ event وانتظره
                ev = _server_events[key]
            else:
                # أنا أفحص — أنشئ event
                ev = _th.Event()
                _server_events[key] = ev
                ev = None  # إشارة أنني الفاحص

        if ev is None:
            # أنا الفاحص
            result = _check_xtream_live(url)
            with _server_lock:
                _server_results[key] = result
            _server_events[key].set()  # أطلق الجميع
            return idx, result, stype
        else:
            # انتظر حتى 10 ثوانٍ
            ev.wait(timeout=10)
            return idx, _server_results.get(key), stype

    if stype == "hls":  return idx, _check_hls(url),  stype
    return idx, _check_http(url), stype

def check_all():
    """فحص كل القنوات بالتوازي مع تقرير مفصل حسب النوع"""
    global _check_cache
    if not channels:
        messagebox.showwarning("تنبيه", "لا توجد قنوات")
        return
    _check_cache.clear()
    _server_results.clear()
    _server_events.clear()

    total = len(channels)
    # total = عدد القنوات الكلي
    # len() = دالة مدمجة تُرجع طول أي متسلسلة (قائمة، نص، tuple)
    # نحفظه في متغير لأننا سنستخدمه كثيراً

    # ---- إظهار إطار التقدم ----
    frm_progress.pack(fill="x", padx=8, pady=3)
    progress_bar.pack(fill="x", padx=8, pady=(0, 6))

    progress_bar["maximum"] = total
    # اضبط الحد الأقصى للشريط = عدد القنوات
    # عندما value = maximum: الشريط يصل 100%

    progress_bar["value"] = 0
    # ابدأ من الصفر
    # [] على عنصر tkinter = الوصول لخصائصه مثل القاموس

    lbl_progress_pct.config(text="0%")
    # lbl_progress_pct = تسمية النسبة المئوية
    # .config(text=...) = عدّل نصها
    # نبدأ بـ 0%

    lbl_progress_count.config(text=f"0 / {total}")
    # lbl_progress_count = تسمية عداد (فُحص / الكلي)
    # f"0 / {total}" = f-string يدمج الرقم في النص
    # مثال: "0 / 500"

    lbl_progress_ok.config(text="✅ 0")
    # lbl_progress_ok = عداد القنوات الشغّالة
    # يبدأ بصفر ويزيد مع كل قناة ناجحة

    lbl_progress_bad.config(text="❌ 0")
    # lbl_progress_bad = عداد القنوات الميتة
    # يبدأ بصفر ويزيد مع كل قناة فاشلة

    btn_check.config(state="disabled")
    # عطّل زر الفحص أثناء الفحص
    # state="disabled" = لا يمكن الضغط عليه (يظهر باهتاً)
    # يمنع بدء فحص ثانٍ في نفس الوقت

    stats = {t: {"ok": 0, "fail": 0} for t in ["xtream_live","xtream_movie","xtream_series","hls","dash","rtmp","udp","http","youtube"]}
    # Dict Comprehension = بناء قاموس في سطر واحد
    # {t: {"ok":0,"fail":0} for t in [...]}
    # t = كل نوع بث في القائمة
    # القيمة = قاموس داخلي يعدّ الناجحة والفاشلة
    # النتيجة: {"xtream_live": {"ok":0,"fail":0}, "hls": {"ok":0,"fail":0}, ...}

    # متغيرات الإحصاء اللحظية — تُحدَّث مع كل قناة
    live_ok  = [0]
    # [0] = قائمة بعنصر واحد بدلاً من متغير عادي
    # السبب: دوال worker الداخلية يمكنها تعديل عناصر القائمة
    # لكن لا يمكنها تعديل متغير عادي (closure limitation)
    # live_ok[0] += 1 يعمل، أما live_ok += 1 فيرمي UnboundLocalError

    live_bad = [0]
    # نفس الفكرة لعداد الميتة

    def worker():
        # دالة مضمَّنة (nested/inner function)
        # تستطيع قراءة وتعديل متغيرات الدالة الخارجية (closure)
        # ستعمل في خيط منفصل عن الخيط الرئيسي

        tasks = [(i, ch["url"]) for i, ch in enumerate(channels)]
        # List Comprehension يبني قائمة tuples
        # كل tuple = (فهرس_القناة, رابطها)
        # سنمرره لـ ex.submit واحدة واحدة

        checked = [0]
        # [0] قائمة بعنصر واحد بدلاً من int عادي
        # السبب: as_completed يعمل في نفس الخيط لكن نحتاج
        # تعديل المتغير من داخل دالة update_ui المجهولة

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            futures = {
                ex.submit(smart_test_channel_grouped, task): task
                for task in tasks
            }

            for future in as_completed(futures):
                # as_completed(futures) = مُولِّد يُعطي كل Future
                # فور انتهائه بغض النظر عن الترتيب
                # هذا هو الفرق الجوهري عن ex.map:
                #   ex.map    = ينتظر القناة 0 قبل 1 قبل 2 ...
                #   as_completed = أيهما انتهت أولاً تظهر أولاً
                # النتيجة: progress bar يتحرك بسلاسة مستمرة

                try:
                    idx, result, stype = future.result()
                except Exception:
                    task = futures[future]
                    idx  = task[0]
                    result, stype = False, "http"

                channels_status[idx] = result

                if stype in stats:
                    if result is True:
                        stats[stype]["ok"] += 1
                        live_ok[0] += 1
                    elif result is False:
                        stats[stype]["fail"] += 1
                        live_bad[0] += 1

                checked[0] += 1

                # تحديث UI كل 10 قنوات — يقلل ضغط الواجهة مع القوائم الكبيرة
                if checked[0] % 10 == 0 or checked[0] == total:
                    pct     = int(checked[0] / total * 100)
                    ok_now  = live_ok[0]
                    bad_now = live_bad[0]
                    v       = checked[0]

                    def update_ui(v=v, p=pct, o=ok_now, b=bad_now):
                        progress_bar.config(value=v)
                        lbl_progress_pct.config(text=f"{p}%")
                        lbl_progress_count.config(text=f"{v} / {total}")
                        lbl_progress_ok.config(text=f"✅ {o}")
                        lbl_progress_bad.config(text=f"❌ {b}")

                    root.after(0, update_ui)

        root.after(0, lambda: finish_check(stats))
        # بعد اكتمال كل الفحوصات: استدعِ finish_check
        # lambda: = دالة مجهولة بدون معاملات تستدعي finish_check

    def finish_check(stats):
        # تُستدعى بعد انتهاء فحص كل القنوات
        # stats = قاموس الإحصائيات المكتملة حسب نوع البث

        frm_progress.pack_forget()
        # أخفِ إطار التقدم كاملاً
        # pack_forget() = عكس pack() — يُزيل من الواجهة دون حذفه

        progress_bar.pack_forget()
        # أخفِ شريط التقدم أيضاً

        btn_check.config(state="normal")
        # أعِد تفعيل زر الفحص
        # state="normal" = عكس "disabled"

        refresh_listbox(entry_search.get())
        # أعِد رسم القائمة مع الرموز الجديدة ✅ و ❌

        ok  = sum(1 for s in channels_status if s is True)
        # Generator Expression داخل sum()
        # يعدّ كل قيمة True في channels_status
        # أكفأ من: len([s for s in channels_status if s is True])

        bad = sum(1 for s in channels_status if s is False)
        # عدد القنوات الميتة

        unk = sum(1 for s in channels_status if s is None)
        # عدد القنوات غير المفحوصة أو غير المعروفة (RTMP/UDP)

        type_names = {"xtream_live":"Xtream حي","xtream_movie":"Xtream أفلام","xtream_series":"Xtream مسلسلات","hls":"HLS","dash":"DASH","rtmp":"RTMP","udp":"UDP","http":"HTTP عام","youtube":"YouTube"}
        # قاموس ترجمة: المفتاح=الكود الداخلي، القيمة=الاسم المقروء

        report = f"📊 نتيجة الفحص الذكي\n{'─'*32}\n✅ شغالة:     {ok}\n❌ ميتة:      {bad}\n❓ غير معروف: {unk}\n📺 الإجمالي:  {len(channels)}\n{'─'*32}\nتفصيل حسب النوع:\n"
        # f-string متعدد الأسطر يبني نص التقرير
        # '─'*32 = تكرار الحرف 32 مرة = خط فاصل

        for stype, c in stats.items():
            # .items() = يُرجع (مفتاح, قيمة) لكل زوج في القاموس
            if c["ok"] + c["fail"] > 0:
                # أضف هذا النوع فقط إذا فُحصت منه قنوات
                report += f"  • {type_names.get(stype,stype)}: ✅{c['ok']} ❌{c['fail']}\n"
                # type_names.get(stype, stype) = ترجمة الاسم، وإذا لم يوجد أرجع الكود نفسه

        messagebox.showinfo("نتيجة الفحص الذكي", report)
        # نافذة معلومات بالتقرير الكامل

    threading.Thread(target=worker, daemon=True).start()
    # threading.Thread = أنشئ خيطاً جديداً
    # target=worker = الدالة التي سيُنفّذها الخيط
    # daemon=True = إذا أُغلق البرنامج يُوقَف الخيط تلقائياً
    # .start() = ابدأ الخيط فوراً

# ==============================================================
# اتصال Xtream API — القلب الجديد للمشروع
# ==============================================================

def get_xtream_credentials():
    """
    يقرأ بيانات الاتصال من حقول الإدخال في تبويب Xtream
    يعيد: (domain, username, password) أو None إذا كانت ناقصة
    """
    domain   = entry_domain.get().strip().rstrip("/")
    # .rstrip("/") = إزالة الـ / من النهاية إذا أضافها المستخدم
    # مثال: "http://server.com/" → "http://server.com"
    username = entry_uname.get().strip()
    password = entry_pass.get().strip()

    if not domain or not username or not password:
        messagebox.showwarning("تنبيه", "أدخل Domain و Username و Password أولاً")
        return None

    # إضافة http:// تلقائياً إذا نسي المستخدم
    if not domain.startswith("http"):
        domain = "http://" + domain

    return domain, username, password

def test_xtream_connection():
    """
    يختبر الاتصال بخادم Xtream ويعرض معلومات الحساب
    يستدعي action=get_user_info من API
    """
    creds = get_xtream_credentials()
    if not creds: return
    domain, username, password = creds

    lbl_xtream_status.config(text="⏳ جاري الاتصال...", fg="orange")
    root.update()
    # root.update() = تحديث الواجهة فوراً (بدونه لا يظهر النص أثناء الانتظار)

    def worker():
        try:
            url = f"{domain}/player_api.php?username={username}&password={password}"
            r   = requests.get(url, timeout=15, verify=False)
            data = r.json()

            user_info = data.get("user_info", {})
            # user_info = قاموس معلومات المستخدم من الخادم

            status      = user_info.get("status", "غير معروف")
            # active = مفعّل, banned = محظور, expired = منتهي

            exp_date    = user_info.get("exp_date", "")
            # تاريخ انتهاء الاشتراك (Unix timestamp أو نص)

            max_conn    = user_info.get("max_connections", "?")
            # أقصى عدد أجهزة متزامنة

            active_conn = user_info.get("active_cons", "?")
            # عدد الاتصالات النشطة حالياً

            server_info = data.get("server_info", {})
            server_url  = server_info.get("url", domain)
            server_port = server_info.get("port", "")
            timezone    = server_info.get("timezone", "")

            msg = (
                f"✅ اتصال ناجح!\n"
                f"{'─'*30}\n"
                f"الحالة:       {status}\n"
                f"ينتهي:        {exp_date}\n"
                f"الاتصالات:    {active_conn} / {max_conn}\n"
                f"{'─'*30}\n"
                f"الخادم:       {server_url}:{server_port}\n"
                f"التوقيت:      {timezone}"
            )
            root.after(0, lambda: lbl_xtream_status.config(text="✅ متصل", fg="green"))
            root.after(0, lambda: messagebox.showinfo("معلومات الخادم", msg))

        except requests.exceptions.ConnectionError:
            root.after(0, lambda: lbl_xtream_status.config(text="❌ فشل الاتصال", fg="red"))
            root.after(0, lambda: messagebox.showerror("خطأ", "تعذر الاتصال. تحقق من Domain والإنترنت."))
        except requests.exceptions.Timeout:
            root.after(0, lambda: lbl_xtream_status.config(text="❌ انتهت المهلة", fg="red"))
            root.after(0, lambda: messagebox.showerror("خطأ", "انتهت مهلة الاتصال."))
        except Exception as e:
            root.after(0, lambda: lbl_xtream_status.config(text="❌ خطأ", fg="red"))
            root.after(0, lambda err=e: messagebox.showerror("خطأ", f"خطأ غير متوقع:\n{err}"))

    threading.Thread(target=worker, daemon=True).start()

# ==============================================================
# جلب القنوات الحية
# ==============================================================

def fetch_live():
    creds = get_xtream_credentials()
    if not creds: return
    domain, username, password = creds
    save_path = filedialog.asksaveasfilename(
        title="حفظ القنوات الحية", defaultextension=".m3u",
        filetypes=[("M3U","*.m3u")], initialfile="القنوات_الحية.m3u")
    if not save_path: return

    lbl_xtream_status.config(text="⏳ جلب القنوات...", fg="orange")
    progress_xtream.pack(fill="x", padx=10, pady=2)
    progress_xtream.config(mode="indeterminate"); progress_xtream.start(10)

    def worker():
        try:
            base     = f"{domain}/player_api.php?username={username}&password={password}"
            # جلب التصنيفات والقنوات بالتوازي
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_cats    = ex.submit(requests.get, base+"&action=get_live_categories", timeout=20, verify=False)
                f_streams = ex.submit(requests.get, base+"&action=get_live_streams",    timeout=30, verify=False)
                cats_raw  = f_cats.result().json()
                streams   = f_streams.result().json()

            if not streams:
                root.after(0, lambda: messagebox.showwarning("تنبيه","لا توجد قنوات")); return

            cat_map = {c["category_id"]: c["category_name"] for c in cats_raw}
            root.after(0, lambda: progress_xtream.config(mode="determinate", maximum=len(streams), value=0))

            with open(save_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for i, s in enumerate(streams):
                    name = s.get("name","بدون اسم"); sid = s.get("stream_id","")
                    cat  = cat_map.get(s.get("category_id",""), s.get("category_name",""))
                    logo = s.get("stream_icon",""); epg = s.get("epg_channel_id","")
                    arc  = s.get("tv_archive",0)
                    url  = f"{domain}/live/{username}/{password}/{sid}.ts"
                    f.write(f'#EXTINF:-1 tvg-id="{epg}" tvg-name="{name}" tvg-logo="{logo}" '
                            f'group-title="{cat}" tvg-chno="{s.get("num","")}" '
                            f'catchup="{"default" if arc else ""}",{name}\n{url}\n')
                    root.after(0, lambda v=i+1: progress_xtream.config(value=v))

            root.after(0, lambda: done_xtream(f"✅ تم حفظ {len(streams)} قناة حية\n{save_path}"))
        except Exception as e:
            root.after(0, lambda err=e: error_xtream(str(err)))

    threading.Thread(target=worker, daemon=True).start()

def fetch_movies():
    creds = get_xtream_credentials()
    if not creds: return
    domain, username, password = creds
    save_path = filedialog.asksaveasfilename(
        title="حفظ الأفلام", defaultextension=".m3u",
        filetypes=[("M3U","*.m3u")], initialfile="الأفلام.m3u")
    if not save_path: return

    lbl_xtream_status.config(text="⏳ جلب الأفلام...", fg="orange")
    progress_xtream.pack(fill="x", padx=10, pady=2)
    progress_xtream.config(mode="indeterminate"); progress_xtream.start(10)

    def worker():
        try:
            base = f"{domain}/player_api.php?username={username}&password={password}"
            # جلب التصنيفات والأفلام بالتوازي
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_cats = ex.submit(requests.get, base+"&action=get_vod_categories", timeout=20, verify=False)
                f_vods = ex.submit(requests.get, base+"&action=get_vod_streams",    timeout=60, verify=False)
                cats_raw = f_cats.result().json()
                vod_list = f_vods.result().json()

            if not vod_list:
                root.after(0, lambda: messagebox.showwarning("تنبيه","لا توجد أفلام")); return

            cat_map = {c["category_id"]: c["category_name"] for c in cats_raw}
            root.after(0, lambda: progress_xtream.config(mode="determinate", maximum=len(vod_list), value=0))

            with open(save_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for i, m in enumerate(vod_list):
                    sid  = m.get("stream_id",""); name = m.get("name","فيلم")
                    cat  = cat_map.get(m.get("category_id",""), m.get("category_name",""))
                    logo = m.get("stream_icon",""); ext = m.get("container_extension","mp4")
                    url  = f"{domain}/movie/{username}/{password}/{sid}.{ext}"
                    f.write(f'#EXTINF:-1 tvg-id="{sid}" tvg-name="{name}" tvg-logo="{logo}" '
                            f'group-title="{cat}" tvg-year="{m.get("year","")}" '
                            f'tvg-rating="{m.get("rating","")}" tvg-director="{m.get("director","")}" '
                            f'tvg-cast="{m.get("cast","").replace(chr(10)," ")[:100]}" '
                            f'tvg-duration="{m.get("duration","")}" '
                            f'tvg-plot="{m.get("plot","").replace(chr(10)," ")[:200]}",{name}\n{url}\n')
                    root.after(0, lambda v=i+1: progress_xtream.config(value=v))

            root.after(0, lambda: done_xtream(f"✅ تم حفظ {len(vod_list)} فيلم\n{save_path}"))
        except Exception as e:
            root.after(0, lambda err=e: error_xtream(str(err)))

    threading.Thread(target=worker, daemon=True).start()

def fetch_series():
    creds = get_xtream_credentials()
    if not creds: return
    domain, username, password = creds
    save_path = filedialog.asksaveasfilename(
        title="حفظ المسلسلات", defaultextension=".m3u",
        filetypes=[("M3U","*.m3u")], initialfile="المسلسلات.m3u")
    if not save_path: return

    lbl_xtream_status.config(text="⏳ جلب المسلسلات...", fg="orange")
    progress_xtream.pack(fill="x", padx=10, pady=2)
    progress_xtream.config(mode="determinate", value=0)

    def worker():
        try:
            base        = f"{domain}/player_api.php?username={username}&password={password}"
            series_list = requests.get(base+"&action=get_series", timeout=30, verify=False).json()
            if not series_list:
                root.after(0, lambda: messagebox.showwarning("تنبيه","لا توجد مسلسلات")); return

            total = len(series_list)
            root.after(0, lambda: progress_xtream.config(maximum=total, value=0))
            done_count = [0]
            results    = [None] * total  # نحفظ الحلقات بالترتيب

            # ---- جلب تفاصيل كل مسلسل بالتوازي ----
            def fetch_one(args):
                idx, s = args
                sid        = s.get("series_id","")
                sname      = s.get("name","مسلسل")
                cover      = s.get("cover","")
                group      = s.get("category_name","مسلسلات")
                rating     = s.get("rating","")
                cast       = s.get("cast","").replace("\n"," ")[:100]
                director   = s.get("director","")
                genre      = s.get("genre","")
                plot       = s.get("plot","").replace("\n"," ")[:200]
                year       = s.get("releaseDate","")
                backdrop   = s.get("backdrop_path",[""])
                bd_url     = backdrop[0] if backdrop else ""
                lines = []
                try:
                    info     = requests.get(f"{base}&action=get_series_info&series_id={sid}",
                                            timeout=15, verify=False).json()
                    episodes = info.get("episodes",{})
                    for sk in sorted(episodes.keys(), key=lambda x: int(x) if x.isdigit() else 0):
                        for ep in episodes[sk]:
                            ep_id  = ep.get("id","")
                            ep_ttl = ep.get("title","")
                            ep_num = ep.get("episode_num",0)
                            s_num  = ep.get("season",0)
                            cont   = ep.get("container_extension","mp4")
                            ep_pl  = ep.get("info",{}).get("plot","").replace("\n"," ")[:200]
                            ep_dur = ep.get("info",{}).get("duration","")
                            ep_rat = ep.get("info",{}).get("rating","")
                            ep_th  = ep.get("info",{}).get("movie_image",cover)
                            try:    code = f"S{int(s_num):02d}E{int(ep_num):02d}"
                            except: code = f"S{sk}E{ep_num}"
                            fname = f"{sname} {code}" + (f" - {ep_ttl}" if ep_ttl else "")
                            url   = f"{domain}/series/{username}/{password}/{ep_id}.{cont}"
                            lines.append(
                                f'#EXTINF:-1 tvg-id="{ep_id}" tvg-logo="{ep_th}" '
                                f'group-title="{sname}" tvg-series="{sname}" '
                                f'tvg-season="{s_num}" tvg-episode="{ep_num}" '
                                f'tvg-year="{year}" tvg-rating="{ep_rat or rating}" '
                                f'tvg-director="{director}" tvg-cast="{cast}" '
                                f'tvg-genre="{genre}" tvg-duration="{ep_dur}" '
                                f'tvg-backdrop="{bd_url}" tvg-plot="{ep_pl or plot}",{fname}\n{url}')
                except: pass
                done_count[0] += 1
                root.after(0, lambda v=done_count[0]: progress_xtream.config(value=v))
                return idx, lines

            # خيوط ديناميكية لجلب تفاصيل المسلسلات
            _sw = min(50, (os.cpu_count() or 4) * 5)
            with ThreadPoolExecutor(max_workers=_sw) as ex:
                futs = {ex.submit(fetch_one, (i,s)): i for i,s in enumerate(series_list)}
                for fut in as_completed(futs):
                    try:
                        idx, lines = fut.result()
                        results[idx] = lines
                    except: pass

            ep_count = 0
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for lines in results:
                    if lines:
                        for l in lines:
                            f.write(l + "\n")
                            ep_count += 1

            root.after(0, lambda: done_xtream(f"✅ {total} مسلسل | {ep_count} حلقة\n{save_path}"))
        except Exception as e:
            root.after(0, lambda err=e: error_xtream(str(err)))

    threading.Thread(target=worker, daemon=True).start()

def done_xtream(msg):
    progress_xtream.stop(); progress_xtream.pack_forget()
    lbl_xtream_status.config(text="✅ تم", fg="green")
    messagebox.showinfo("اكتمل", msg)

def error_xtream(err):
    progress_xtream.stop(); progress_xtream.pack_forget()
    lbl_xtream_status.config(text="❌ فشل", fg="red")
    messagebox.showerror("خطأ", f"فشل الجلب:\n{err}")

# ==============================================================
# بناء الواجهة الرسومية
# ==============================================================


# ==============================================================
# اختيار وضع التشغيل: محلي أم ويب
# ==============================================================
import sys as _sys
import socket as _socket
import threading as _web_threading

def _choose_mode():
    """نافذة صغيرة تسأل: محلي أم ويب أم عالمي؟"""
    _mode = ["local"]
    _win = tk.Tk()
    _win.title("Opy IPTV — اختر الوضع")
    _win.geometry("580x240")
    _win.resizable(False, False)
    _win.configure(bg="#1a1a2e")
    _win.eval('tk::PlaceWindow . center')

    tk.Label(_win, text="🎬 Opy IPTV V18.9",
             bg="#1a1a2e", fg="#e94560",
             font=("Arial", 16, "bold")).pack(pady=(22, 4))
    tk.Label(_win, text="كيف تريد تشغيل البرنامج؟",
             bg="#1a1a2e", fg="#aaa",
             font=("Arial", 10)).pack(pady=(0, 18))

    _bf = tk.Frame(_win, bg="#1a1a2e")
    _bf.pack()

    def _pick_local():
        _mode[0] = "local"; _win.destroy()

    def _pick_web():
        _mode[0] = "web"; _win.destroy()

    def _pick_cloud():
        _mode[0] = "cloudflare"; _win.destroy()

    tk.Button(_bf,
              text="🖥  محلي\nواجهة رسومية كاملة",
              bg="#2980b9", fg="white",
              font=("Arial", 11, "bold"),
              width=14, height=3,
              relief="flat", cursor="hand2",
              command=_pick_local).pack(side="left", padx=8)

    tk.Button(_bf,
              text="📱  ويب\nمن متصفح الهاتف",
              bg="#27ae60", fg="white",
              font=("Arial", 11, "bold"),
              width=14, height=3,
              relief="flat", cursor="hand2",
              command=_pick_web).pack(side="left", padx=8)

    tk.Button(_bf,
              text="🌍  عالمي\nCloudflare Tunnel",
              bg="#8e44ad", fg="white",
              font=("Arial", 11, "bold"),
              width=14, height=3,
              relief="flat", cursor="hand2",
              command=_pick_cloud).pack(side="left", padx=8)

    _win.mainloop()
    return _mode[0]


_WEB_HTML = """<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Opy IPTV V18.9</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,sans-serif;background:#1a1a2e;color:#eee;min-height:100vh}
.header{background:#16213e;padding:12px 16px;display:flex;align-items:center;gap:10px;border-bottom:2px solid #e94560}
.header h1{color:#e94560;font-size:20px}
.header span{color:#aaa;font-size:13px}
.tabs{display:flex;background:#16213e;border-bottom:1px solid #333}
.tab{padding:12px 20px;cursor:pointer;color:#aaa;border-bottom:3px solid transparent;font-size:14px;user-select:none;-webkit-tap-highlight-color:transparent;touch-action:manipulation}
.tab.active{color:#e94560;border-bottom-color:#e94560}
.content{padding:12px}
.panel{display:none}
.panel.active{display:block}
.card{background:#16213e;border-radius:8px;padding:12px;margin-bottom:10px}
.card-title{color:#e94560;font-size:13px;font-weight:bold;margin-bottom:8px}
input,textarea{width:100%;padding:8px 10px;background:#0f3460;border:1px solid #333;border-radius:6px;color:#eee;font-size:14px;margin-bottom:6px}
input:focus{border-color:#e94560;outline:none}
.btn{padding:9px 16px;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:bold;margin:3px}
.btn-green{background:#27ae60;color:white}
.btn-blue{background:#2980b9;color:white}
.btn-red{background:#e74c3c;color:white}
.btn-orange{background:#e67e22;color:white}
.btn-gray{background:#555;color:white}
.btn-purple{background:#8e44ad;color:white}
.btn-row{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
.search-row{display:flex;gap:8px;align-items:center;margin-bottom:8px}
.search-row input{margin:0;flex:1}
.count-badge{background:#0f3460;border-radius:12px;padding:4px 10px;font-size:12px;color:#aaa;white-space:nowrap}
.ch-list{max-height:45vh;overflow-y:auto;border-radius:6px;background:#0f3460}
.ch-item{padding:10px 12px;border-bottom:1px solid #1a1a2e;cursor:pointer;display:flex;justify-content:space-between;align-items:center;font-size:13px}
.ch-item.selected{background:#1a4a7a}
.ch-name{font-weight:bold;color:#eee}
.ch-cat{color:#888;font-size:11px}
.progress-box{background:#16213e;border-radius:8px;padding:12px;margin-bottom:10px;display:none}
.progress-bar-bg{background:#0f3460;border-radius:4px;height:12px;overflow:hidden;margin:8px 0}
.progress-bar-fill{background:linear-gradient(90deg,#27ae60,#2ecc71);height:100%;border-radius:4px;transition:width 0.3s;width:0%}
.progress-stats{display:flex;gap:12px;font-size:13px;flex-wrap:wrap}
.pct{font-size:20px;font-weight:bold;color:#e94560}
.ok-count{color:#27ae60;font-weight:bold}
.bad-count{color:#e74c3c;font-weight:bold}
.msg{padding:8px 12px;border-radius:6px;margin-bottom:8px;font-size:13px;display:none}
.msg.ok{background:#1a4a2a;color:#2ecc71;display:block}
.msg.err{background:#4a1a1a;color:#e74c3c;display:block}
.msg.inf{background:#1a3a4a;color:#3498db;display:block}
.replace-row{display:flex;gap:6px}
.replace-row input{margin:0}
</style>
</head>
<body>
<div class="header"><h1>🎬 Opy IPTV</h1><span>Wael</span></div>
<div class="tabs">
  <div class="tab active" onclick="switchTab('editor',this)">📋 محرر M3U</div>
  <div class="tab" onclick="switchTab('xtream',this)">📡 Xtream API</div>
</div>
<div id="panel-editor" class="panel active content">
  <div class="card">
    <div class="card-title">📁 تحميل ملف M3U</div>
    <input type="file" id="fileInput" accept=".m3u,.m3u8,.txt" onchange="uploadFile()">
    <div id="msg-load" class="msg"></div>
  </div>
  <div class="search-row">
    <input type="text" id="searchBox" placeholder="🔍 بحث..." oninput="filterChannels()">
    <div class="count-badge" id="countBadge">0 قناة</div>
  </div>
  <div class="ch-list" id="chList"></div>
  <div class="card" style="margin-top:10px">
    <div class="card-title">✏ بيانات القناة</div>
    <input type="text" id="inName" placeholder="الاسم">
    <input type="text" id="inCat" placeholder="التصنيف">
    <input type="text" id="inUrl" placeholder="الرابط">
    <div class="btn-row">
      <button class="btn btn-green" onclick="addChannel()">➕ إضافة</button>
      <button class="btn btn-blue" onclick="saveEdit()">✏ حفظ تعديل</button>
      <button class="btn btn-red" onclick="deleteSelected()">🗑 حذف</button>
    </div>
  </div>
  <div class="card">
    <div class="card-title">🔄 استبدال في الأسماء</div>
    <div class="replace-row">
      <input type="text" id="replOld" placeholder="قديم">
      <input type="text" id="replNew" placeholder="جديد">
      <button class="btn btn-purple" onclick="replaceName()">🔄</button>
    </div>
  </div>
  <div class="card">
    <div class="card-title">📡 فحص القنوات</div>
    <div class="btn-row">
      <button class="btn btn-orange" id="btnCheck" onclick="startCheck()">🔍 فحص ذكي</button>
      <button class="btn btn-red" onclick="selectDead()">❌ تحديد الميتة</button>
      <button class="btn btn-green" onclick="selectLive()">✅ تحديد الشغالة</button>
    </div>
    <div class="progress-box" id="progressBox">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span class="pct" id="pctText">0%</span>
        <div class="progress-stats">
          <span id="countText" style="color:#aaa">0 / 0</span>
          <span class="ok-count" id="okText">✅ 0</span>
          <span class="bad-count" id="badText">❌ 0</span>
        </div>
      </div>
      <div class="progress-bar-bg"><div class="progress-bar-fill" id="progressFill"></div></div>
    </div>
    <div id="msg-check" class="msg"></div>
  </div>
  <div class="card">
    <div class="card-title">💾 تصدير</div>
    <button class="btn btn-blue" onclick="downloadM3U()">⬇ تحميل M3U</button>
  </div>
</div>
<div id="panel-xtream" class="panel content">
  <div class="card">
    <div class="card-title">🔐 بيانات الاتصال</div>
    <input type="text" id="xDomain" placeholder="http://server.com:8080">
    <input type="text" id="xUser" placeholder="Username">
    <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
      <input type="password" id="xPass" placeholder="Password" style="margin:0;flex:1">
      <button class="btn btn-gray" onclick="togglePass()" id="btnShowPass" style="white-space:nowrap">👁 عرض</button>
    </div>
    <div class="btn-row">
      <button class="btn btn-blue" onclick="testXtream()">🔌 اختبار الاتصال</button>
    </div>
    <div id="msg-xtream-conn" class="msg"></div>
  </div>
  <div class="card">
    <div class="card-title">📥 جلب المحتوى</div>

    <!-- القنوات الحية -->
    <div style="background:#0f3460;border-radius:8px;padding:12px;margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <span style="font-size:24px">📺</span>
        <div style="flex:1">
          <div style="font-weight:bold">القنوات الحية</div>
          <div style="color:#888;font-size:11px">اسم، تصنيف، شعار، EPG</div>
        </div>
        <button class="btn btn-green" onclick="fetchLive()" id="btnLive">⬇ جلب</button>
      </div>
      <div id="progressLive" style="display:none">
        <div class="progress-bar-bg"><div class="progress-bar-fill" id="fillLive" style="width:0%;transition:width 0.4s;background:linear-gradient(90deg,#27ae60,#2ecc71)"></div></div>
        <div style="display:flex;justify-content:space-between;font-size:12px;color:#aaa;margin-top:3px"><span id="pctLive">0%</span><span id="cntLive">جاري الجلب...</span></div>
      </div>
    </div>

    <!-- الأفلام -->
    <div style="background:#0f3460;border-radius:8px;padding:12px;margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <span style="font-size:24px">🎬</span>
        <div style="flex:1">
          <div style="font-weight:bold">الأفلام</div>
          <div style="color:#888;font-size:11px">ملصق، تقييم، مخرج، ممثلين</div>
        </div>
        <button class="btn btn-purple" onclick="fetchMovies()" id="btnMovies">⬇ جلب</button>
      </div>
      <div id="progressMovies" style="display:none">
        <div class="progress-bar-bg"><div class="progress-bar-fill" id="fillMovies" style="width:0%;transition:width 0.4s;background:linear-gradient(90deg,#8e44ad,#9b59b6)"></div></div>
        <div style="display:flex;justify-content:space-between;font-size:12px;color:#aaa;margin-top:3px"><span id="pctMovies">0%</span><span id="cntMovies">جاري الجلب...</span></div>
      </div>
    </div>

    <!-- المسلسلات -->
    <div style="background:#0f3460;border-radius:8px;padding:12px;margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <span style="font-size:24px">📡</span>
        <div style="flex:1">
          <div style="font-weight:bold">المسلسلات</div>
          <div style="color:#888;font-size:11px">S01E01، موسم، حلقة، ملخص</div>
        </div>
        <button class="btn btn-orange" onclick="fetchSeries()" id="btnSeries">⬇ جلب</button>
      </div>
      <div id="progressSeries" style="display:none">
        <div class="progress-bar-bg"><div class="progress-bar-fill" id="fillSeries" style="width:0%;transition:width 0.4s;background:linear-gradient(90deg,#e67e22,#f39c12)"></div></div>
        <div style="display:flex;justify-content:space-between;font-size:12px;color:#aaa;margin-top:3px"><span id="pctSeries">0%</span><span id="cntSeries">جاري الجلب...</span></div>
      </div>
    </div>

    <div id="msg-xtream" class="msg"></div>
    <!-- زر تحميل مباشر يظهر بعد الجلب -->
    <div id="downloadBox" style="display:none;margin-top:8px">
      <button class="btn btn-blue" style="width:100%;padding:12px;font-size:15px" onclick="downloadM3U()">⬇ تحميل الملف M3U</button>
    </div>
  </div>
  <div class="card">
    <div class="card-title">ℹ ملاحظات</div>
    <div style="color:#888;font-size:12px;line-height:1.8">
      <div>• القنوات الحية: سريعة الجلب — ملف M3U واحد بكل القنوات</div>
      <div>• الأفلام: متوسطة السرعة — قد تستغرق دقيقة لمكتبات كبيرة</div>
      <div>• المسلسلات: بطيئة — تجلب تفاصيل كل مسلسل على حدة</div>
      <div>• بعد الجلب يمكنك فتح الملف في تبويب المحرر</div>
    </div>
  </div>
</div>
<script>
var allChannels=[],filteredIdx=[],selectedIdx=new Set(),checkInterval=null,webStatuses=[];
function switchTab(t,el){document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));el.classList.add('active');document.getElementById('panel-'+t).classList.add('active');}
async function uploadFile(){
  var input=document.getElementById('fileInput');
  var file=input.files[0];
  if(!file)return;
  showMsg('msg-load','⏳ جاري تحميل الملف...','inf');
  var fd=new FormData();
  fd.append('file', file);
  try{
    var r=await fetch('/api/load_m3u',{method:'POST',body:fd});
    var data=await r.json();
    if(data.error){showMsg('msg-load','❌ '+data.error,'err');return;}
    allChannels=data.channels.map(ch=>({...ch,status:null}));
    showMsg('msg-load','✅ تم تحميل '+allChannels.length+' قناة','ok');
    renderList();
  }catch(e){showMsg('msg-load','❌ فشل الإرسال: '+e,'err');}
  finally{ input.value=''; }
}
function renderList(filter){filter=(filter||'').toLowerCase();filteredIdx=[];allChannels.forEach(function(ch,i){if(!filter||ch.name.toLowerCase().includes(filter)||ch.category.toLowerCase().includes(filter))filteredIdx.push(i);});document.getElementById('countBadge').textContent=filteredIdx.length+' / '+allChannels.length;var list=document.getElementById('chList');list.innerHTML=filteredIdx.map(function(ri){var ch=allChannels[ri];var st=ch.status===true?'✅':ch.status===false?'❌':ch.status===null&&window._checkDone?'—':'';var sel=selectedIdx.has(ri)?'selected':'';return '<div class="ch-item '+sel+'" onclick="selectItem('+ri+')"><div><div class="ch-name">'+ch.name+'</div><div class="ch-cat">'+ch.category+'</div></div><span>'+st+'</span></div>';}).join('');}
function filterChannels(){renderList(document.getElementById('searchBox').value);}
function selectItem(ri){selectedIdx.clear();selectedIdx.add(ri);var ch=allChannels[ri];document.getElementById('inName').value=ch.name;document.getElementById('inCat').value=ch.category;document.getElementById('inUrl').value=ch.url;renderList(document.getElementById('searchBox').value);}
function addChannel(){var name=document.getElementById('inName').value.trim();var cat=document.getElementById('inCat').value.trim();var url=document.getElementById('inUrl').value.trim();if(!name||!url){alert('الاسم والرابط مطلوبان');return;}allChannels.push({name:name,category:cat,url:url,extinf:'#EXTINF:-1 group-title="'+cat+'",'+name,status:null});renderList(document.getElementById('searchBox').value);}
function saveEdit(){if(!selectedIdx.size){alert('اختر قناة أولاً');return;}var ri=[...selectedIdx][0];var ch=allChannels[ri];ch.name=document.getElementById('inName').value.trim();ch.category=document.getElementById('inCat').value.trim();ch.url=document.getElementById('inUrl').value.trim();var parts=ch.extinf.split(',');parts[parts.length-1]=ch.name;ch.extinf=parts.join(',');renderList(document.getElementById('searchBox').value);}
function deleteSelected(){if(!selectedIdx.size){alert('اختر قناة أولاً');return;}[...selectedIdx].sort((a,b)=>b-a).forEach(i=>allChannels.splice(i,1));selectedIdx.clear();renderList(document.getElementById('searchBox').value);}
function replaceName(){var old=document.getElementById('replOld').value;var newt=document.getElementById('replNew').value;if(!old)return;var changed=0;allChannels.forEach(function(ch){if(ch.name.includes(old)){ch.name=ch.name.split(old).join(newt);var parts=ch.extinf.split(',');parts[parts.length-1]=ch.name;ch.extinf=parts.join(',');changed++;}});renderList(document.getElementById('searchBox').value);alert('تم تعديل '+changed+' قناة');}
function selectDead(){selectedIdx.clear();allChannels.forEach(function(ch,i){if(ch.status===false)selectedIdx.add(i);});renderList(document.getElementById('searchBox').value);}
function selectLive(){selectedIdx.clear();allChannels.forEach(function(ch,i){if(ch.status===true)selectedIdx.add(i);});renderList(document.getElementById('searchBox').value);}
async function startCheck(){if(!allChannels.length){alert('لا توجد قنوات');return;}document.getElementById('btnCheck').disabled=true;document.getElementById('progressBox').style.display='block';document.getElementById('progressFill').style.width='0%';document.getElementById('pctText').textContent='0%';window._checkDone=false;showMsg('msg-check','⏳ جاري الفحص...','inf');await fetch('/api/start_check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channels:allChannels.map(ch=>ch.url)})});checkInterval=setInterval(pollProgress,200);}
async function pollProgress(){var data=await(await fetch('/api/check_progress')).json();var pct=data.total?Math.round(data.checked/data.total*100):0;document.getElementById('pctText').textContent=pct+'%';document.getElementById('countText').textContent=data.checked+' / '+data.total;document.getElementById('okText').textContent='✅ '+data.ok;document.getElementById('badText').textContent='❌ '+data.bad;document.getElementById('progressFill').style.width=pct+'%';if(data.done){clearInterval(checkInterval);var result=await(await fetch('/api/check_results')).json();window._checkDone=true;result.statuses.forEach(function(st,i){if(i<allChannels.length)allChannels[i].status=(st===true?true:st===false?false:null);});renderList(document.getElementById('searchBox').value);document.getElementById('btnCheck').disabled=false;showMsg('msg-check','✅ '+data.ok+' شغالة  ❌ '+data.bad+' ميتة  من '+data.total,'ok');}}
async function downloadM3U(){
  if(!allChannels.length){alert('لا توجد قنوات');return;}
  var defName='playlist';
  if(allChannels.length){
    var u=(allChannels[0].url||'').toLowerCase();
    if(u.includes('/movie/'))defName='Movies';
    else if(u.includes('/series/'))defName='Series';
    else if(u.includes('/live/')||u.endsWith('.ts'))defName='Channels';
  }
  var fname=prompt('اسم الملف:',defName);
  if(fname===null)return;
  if(!fname.trim())fname=defName;
  if(!fname.toLowerCase().endsWith('.m3u'))fname+='.m3u';
  var r=await fetch('/api/export_m3u',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channels:allChannels})});
  var text=await r.text();
  try{var blob=new Blob([text],{type:'audio/x-mpegurl'});var url=URL.createObjectURL(blob);var a=document.createElement('a');a.href=url;a.download=fname;document.body.appendChild(a);a.click();document.body.removeChild(a);setTimeout(function(){URL.revokeObjectURL(url);},1000);}catch(e){window.open('/api/download_m3u_last','_blank');}
}
function togglePass(){var f=document.getElementById('xPass');var b=document.getElementById('btnShowPass');if(f.type==='password'){f.type='text';b.textContent='🙈 إخفاء';}else{f.type='password';b.textContent='👁 عرض';}}
async function testXtream(){var domain=document.getElementById('xDomain').value.trim();var user=document.getElementById('xUser').value.trim();var pass=document.getElementById('xPass').value.trim();if(!domain||!user||!pass){alert('أدخل كل البيانات');return;}showMsg('msg-xtream-conn','⏳ جاري الاتصال...','inf');var data=await(await fetch('/api/xtream_test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({domain:domain,username:user,password:pass})})).json();if(data.error){showMsg('msg-xtream-conn','❌ '+data.error,'err');return;}showMsg('msg-xtream-conn','✅ متصل | الحالة: '+data.status+' | ينتهي: '+data.exp+' | الاتصالات: '+data.active+'/'+data.max+' | الخادم: '+data.server+' | التوقيت: '+data.timezone,'ok');}
function _getXCreds(){var d=document.getElementById('xDomain').value.trim();var u=document.getElementById('xUser').value.trim();var p=document.getElementById('xPass').value.trim();if(!d||!u||!p){alert('أدخل كل بيانات الاتصال أولاً');return null;}return{domain:d,username:u,password:p};}
async function fetchLive(){var c=_getXCreds();if(!c)return;document.getElementById('btnLive').disabled=true;document.getElementById('progressLive').style.display='block';document.getElementById('fillLive').style.width='0%';document.getElementById('pctLive').textContent='0%';document.getElementById('cntLive').textContent='جاري الجلب...';showMsg('msg-xtream','⏳ جاري جلب القنوات...','inf');var data=await(await fetch('/api/xtream_live',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)})).json();document.getElementById('btnLive').disabled=false;if(data.error){showMsg('msg-xtream','❌ '+data.error,'err');document.getElementById('progressLive').style.display='none';return;}allChannels=data.channels.map(ch=>({...ch,status:null}));document.getElementById('fillLive').style.width='100%';document.getElementById('pctLive').textContent='100%';document.getElementById('cntLive').textContent=allChannels.length+' قناة';showMsg('msg-xtream','✅ تم جلب '+allChannels.length+' قناة','ok');renderList();document.getElementById('downloadBox').style.display='block';}

async function fetchMovies(){var c=_getXCreds();if(!c)return;document.getElementById('btnMovies').disabled=true;document.getElementById('progressMovies').style.display='block';document.getElementById('fillMovies').style.width='0%';document.getElementById('pctMovies').textContent='0%';document.getElementById('cntMovies').textContent='جاري الجلب...';showMsg('msg-xtream','⏳ جاري جلب الأفلام...','inf');await fetch('/api/xtream_movies_start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)});var mi=setInterval(async function(){var p=await(await fetch('/api/xtream_movies_progress')).json();var pct=p.total?Math.round(p.done/p.total*100):0;document.getElementById('fillMovies').style.width=pct+'%';document.getElementById('pctMovies').textContent=pct+'%';document.getElementById('cntMovies').textContent=p.done+' / '+p.total;if(p.finished){clearInterval(mi);document.getElementById('btnMovies').disabled=false;if(p.error){showMsg('msg-xtream','❌ '+p.error,'err');return;}allChannels=p.channels.map(ch=>({...ch,status:null}));showMsg('msg-xtream','✅ تم جلب '+allChannels.length+' فيلم','ok');renderList();document.getElementById('downloadBox').style.display='block';}},300);}

async function fetchSeries(){var c=_getXCreds();if(!c)return;document.getElementById('btnSeries').disabled=true;document.getElementById('progressSeries').style.display='block';document.getElementById('fillSeries').style.width='0%';document.getElementById('pctSeries').textContent='0%';document.getElementById('cntSeries').textContent='جاري الجلب...';showMsg('msg-xtream','⏳ جاري جلب المسلسلات...','inf');await fetch('/api/xtream_series_start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)});var si=setInterval(async function(){var p=await(await fetch('/api/xtream_series_progress')).json();var pct=p.total?Math.round(p.done/p.total*100):0;document.getElementById('fillSeries').style.width=pct+'%';document.getElementById('pctSeries').textContent=pct+'%';document.getElementById('cntSeries').textContent=p.done+' / '+(p.total||'?')+' مسلسل';if(p.finished){clearInterval(si);document.getElementById('btnSeries').disabled=false;if(p.error){showMsg('msg-xtream','❌ '+p.error,'err');return;}allChannels=p.channels.map(ch=>({...ch,status:null}));showMsg('msg-xtream','✅ '+p.series_count+' مسلسل | '+p.ep_count+' حلقة','ok');renderList();document.getElementById('downloadBox').style.display='block';}},500);}
function showMsg(id,text,type){var el=document.getElementById(id);el.textContent=text;el.className='msg '+type;}
</script>
</body>
</html>"""

_web_channels_status = []
_web_check_progress  = {"checked":0,"total":0,"ok":0,"bad":0,"done":False,"running":False}

def _run_web_mode():
    try:
        from flask import Flask as _Flask, request as _req, jsonify as _json, Response as _Resp
    except ImportError:
        import tkinter.messagebox as _mb
        _mb.showerror("خطأ", "Flask غير مثبتة.\nشغّل في Terminal:\n  pip install flask")
        return

    _app = _Flask(__name__)
    _app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB

    @_app.route("/")
    def _index():
        return _WEB_HTML

    @_app.route("/api/load_m3u", methods=["POST"])
    def _load():
        # قراءة الملف مباشرة أو من form content
        try:
            if "file" in _req.files:
                f   = _req.files["file"]
                raw = f.read()
                # نجرب UTF-8 ثم latin-1 كـ fallback
                try:    txt = raw.decode("utf-8")
                except: txt = raw.decode("latin-1", errors="ignore")
            else:
                txt = _req.form.get("content", "")
        except Exception as e:
            return _json({"error": str(e), "channels": [], "count": 0})

        _chs = []
        extinf_line = None
        for raw_line in txt.splitlines():
            line = raw_line.strip()
            if not line: continue
            if line.startswith("#EXTINF"):
                extinf_line = line
            elif extinf_line and not line.startswith("#"):
                nm  = extinf_line.split(",")[-1].strip()
                m   = re.search(r'group-title="([^"]+)"', extinf_line) or \
                      re.search(r'tvg-category="([^"]+)"', extinf_line)
                cat = m.group(1) if m else ""
                _chs.append({"extinf": extinf_line, "name": nm, "category": cat, "url": line})
                extinf_line = None
        return _json({"channels": _chs, "count": len(_chs)})

    @_app.route("/api/start_check", methods=["POST"])
    def _start_check():
        global _web_channels_status, _web_check_progress
        urls = _req.get_json().get("channels", [])
        _web_channels_status = [None] * len(urls)
        # نصفّر قبل بدء الخيط حتى يرى المتصفح القيمة الصحيحة فوراً
        _web_check_progress = {"checked": 0, "total": len(urls), "ok": 0, "bad": 0, "done": False, "running": True}
        _check_cache.clear()
        _server_results.clear()
        _server_events.clear()
        _progress_lock = _th.Lock()

        def _do():
            from concurrent.futures import ThreadPoolExecutor, as_completed as _ac
            def _test(iu):
                idx, url = iu
                u = url.lower()
                if u.startswith("rtmp://") or u.startswith("udp://"): return idx, None
                stype = detect_stream_type(url)
                if stype == "xtream_live":
                    key = _extract_xtream_key(url)
                    with _server_lock:
                        if key in _server_results:
                            return idx, _server_results[key]
                        if key in _server_events:
                            ev = _server_events[key]
                        else:
                            ev = _th.Event()
                            _server_events[key] = ev
                            ev = None
                    if ev is None:
                        result = _check_xtream_live(url)
                        with _server_lock:
                            _server_results[key] = result
                        _server_events[key].set()
                        return idx, result
                    else:
                        ev.wait(timeout=10)
                        return idx, _server_results.get(key)
                if stype == "hls": return idx, _check_hls(url)
                return idx, _check_http(url)
            with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
                futs = {ex.submit(_test, (i, u)): i for i, u in enumerate(urls)}
                for fut in _ac(futs):
                    try:
                        idx, res = fut.result()
                    except:
                        idx = futs[fut]
                        res = False
                    _web_channels_status[idx] = res
                    with _progress_lock:
                        _web_check_progress["checked"] += 1
                        if res is True:  _web_check_progress["ok"]  += 1
                        elif res is False: _web_check_progress["bad"] += 1
            # أي قناة لم تُفحص (None) تُعدّ غير معروفة
            _web_check_progress["done"] = True

        _web_threading.Thread(target=_do, daemon=True).start()
        return _json({"started": True})

    @_app.route("/api/check_progress")
    def _prog(): return _json(_web_check_progress)

    @_app.route("/api/check_results")
    def _results(): return _json({"statuses":_web_channels_status})

    _last_m3u = {"content": ""}

    @_app.route("/api/export_m3u", methods=["POST"])
    def _export():
        chs  = _req.get_json().get("channels",[])
        # كتابة دفعة واحدة — أسرع من التكرار
        lines = ["#EXTM3U"]
        for ch in chs:
            lines.append(ch.get("extinf", f'#EXTINF:-1 group-title="{ch.get("category","")}",{ch.get("name","")}'))
            lines.append(ch.get("url",""))
        out = "\n".join(lines) + "\n"
        _last_m3u["content"] = out
        return _Resp(out, mimetype="audio/x-mpegurl",
                     headers={"Content-Disposition": "attachment; filename=opy_iptv.m3u"})

    @_app.route("/api/download_m3u_last")
    def _download_last():
        content = _last_m3u.get("content", "#EXTM3U\n")
        return _Resp(content, mimetype="audio/x-mpegurl",
                     headers={"Content-Disposition": "attachment; filename=opy_iptv.m3u"})

    @_app.route("/api/xtream_test", methods=["POST"])
    def _xtest():
        d = _req.get_json()
        dom = d.get("domain","").rstrip("/")
        if not dom.startswith("http"): dom = "http://" + dom
        try:
            r  = requests.get(f"{dom}/player_api.php?username={d['username']}&password={d['password']}",
                              timeout=15, verify=False, headers={"User-Agent": USER_AGENT}).json()
            ui = r.get("user_info", {})
            si = r.get("server_info", {})
            return _json({
                "status":   ui.get("status","—"),
                "exp":      ui.get("exp_date","—"),
                "max":      ui.get("max_connections","—"),
                "active":   ui.get("active_cons","—"),
                "server":   f"{si.get('url',dom)}:{si.get('port','')}",
                "timezone": si.get("timezone","—"),
            })
        except Exception as e: return _json({"error":str(e)})

    _movies_progress = {"done":0,"total":0,"finished":False,"channels":[],"error":""}

    @_app.route("/api/xtream_movies_start", methods=["POST"])
    def _xmovies_start():
        nonlocal _movies_progress
        d   = _req.get_json()
        dom = d.get("domain","").rstrip("/")
        if not dom.startswith("http"): dom = "http://" + dom
        u, p = d.get("username",""), d.get("password","")
        _movies_progress = {"done":0,"total":0,"finished":False,"channels":[],"error":""}

        def _do():
            nonlocal _movies_progress
            try:
                base  = f"{dom}/player_api.php?username={u}&password={p}"
                cats  = {c["category_id"]: c["category_name"] for c in
                         requests.get(base+"&action=get_vod_categories", timeout=20, verify=False).json()}
                vods  = requests.get(base+"&action=get_vod_streams", timeout=60, verify=False).json()
                total = len(vods)
                _movies_progress["total"] = total
                chs = []
                for i, m in enumerate(vods):
                    sid      = m.get("stream_id","")
                    name     = m.get("name","فيلم")
                    cat      = cats.get(m.get("category_id",""), m.get("category_name",""))
                    logo     = m.get("stream_icon","")
                    ext      = m.get("container_extension","mp4")
                    rating   = m.get("rating","")
                    year     = m.get("year","")
                    director = m.get("director","")
                    cast     = m.get("cast","").replace("\n"," ")[:100]
                    plot     = m.get("plot","").replace("\n"," ")[:200]
                    trailer  = m.get("youtube_trailer","")
                    url      = f"{dom}/movie/{u}/{p}/{sid}.{ext}"
                    extinf   = (f'#EXTINF:-1 tvg-id="{sid}" tvg-logo="{logo}" group-title="{cat}" '
                                f'tvg-year="{year}" tvg-rating="{rating}" tvg-director="{director}" '
                                f'tvg-cast="{cast}" tvg-trailer="https://youtube.com/watch?v={trailer}" '
                                f'tvg-plot="{plot}",{name}')
                    chs.append({"name":name,"category":cat,"url":url,"extinf":extinf})
                    _movies_progress["done"] = i + 1
                _movies_progress.update({"finished":True,"channels":chs})
            except Exception as e:
                _movies_progress.update({"finished":True,"error":str(e)})

        _web_threading.Thread(target=_do, daemon=True).start()
        return _json({"started": True})

    @_app.route("/api/xtream_movies_progress")
    def _xmovies_progress():
        p = dict(_movies_progress)
        if not p.get("finished"):
            p.pop("channels", None)
        return _json(p)

    @_app.route("/api/xtream_movies", methods=["POST"])
    def _xmovies():
        # fallback قديم — غير مستخدم لكن نبقيه للتوافق
        d = _req.get_json()
        dom = d.get("domain","").rstrip("/")
        if not dom.startswith("http"): dom = "http://" + dom
        u, p = d.get("username",""), d.get("password","")
        try:
            base  = f"{dom}/player_api.php?username={u}&password={p}"
            cats  = {c["category_id"]: c["category_name"] for c in
                     requests.get(base+"&action=get_vod_categories", timeout=20, verify=False).json()}
            vods  = requests.get(base+"&action=get_vod_streams", timeout=60, verify=False).json()
            chs = []
            for m in vods:
                sid  = m.get("stream_id",""); name = m.get("name","فيلم")
                cat  = cats.get(m.get("category_id",""), m.get("category_name",""))
                logo = m.get("stream_icon",""); ext = m.get("container_extension","mp4")
                url  = f"{dom}/movie/{u}/{p}/{sid}.{ext}"
                extinf = f'#EXTINF:-1 tvg-logo="{logo}" group-title="{cat}",{name}'
                chs.append({"name":name,"category":cat,"url":url,"extinf":extinf})
            return _json({"channels": chs})
        except Exception as e: return _json({"error": str(e)})

    # حالة جلب المسلسلات (global للوصول من route آخر)
    _series_progress = {"done":0,"total":0,"finished":False,"channels":[],"ep_count":0,"series_count":0,"error":""}

    @_app.route("/api/xtream_series_start", methods=["POST"])
    def _xseries_start():
        nonlocal _series_progress
        d   = _req.get_json()
        dom = d.get("domain","").rstrip("/")
        if not dom.startswith("http"): dom = "http://" + dom
        u, p = d.get("username",""), d.get("password","")
        _series_progress = {"done":0,"total":0,"finished":False,"channels":[],"ep_count":0,"series_count":0,"error":""}

        def _do():
            nonlocal _series_progress
            try:
                base        = f"{dom}/player_api.php?username={u}&password={p}"
                series_list = requests.get(base+"&action=get_series", timeout=30, verify=False).json()
                total       = len(series_list)
                _series_progress["total"] = total
                results    = [None] * total
                done_count = [0]

                def fetch_one(args):
                    idx, s = args
                    sid      = s.get("series_id","");  sname = s.get("name","مسلسل")
                    cover    = s.get("cover","");       rating = s.get("rating","")
                    cast     = s.get("cast","").replace("\n"," ")[:100]
                    director = s.get("director","");    genre = s.get("genre","")
                    plot     = s.get("plot","").replace("\n"," ")[:200]
                    year     = s.get("releaseDate","")
                    backdrop = s.get("backdrop_path",[""])
                    bd_url   = backdrop[0] if backdrop else ""
                    lines = []
                    try:
                        info     = requests.get(f"{base}&action=get_series_info&series_id={sid}",
                                                timeout=15, verify=False).json()
                        episodes = info.get("episodes",{})
                        for sk in sorted(episodes.keys(), key=lambda x: int(x) if x.isdigit() else 0):
                            for ep in episodes[sk]:
                                ep_id  = ep.get("id","");      ep_ttl = ep.get("title","")
                                ep_num = ep.get("episode_num",0); s_num = ep.get("season",0)
                                cont   = ep.get("container_extension","mp4")
                                ep_pl  = ep.get("info",{}).get("plot","").replace("\n"," ")[:200]
                                ep_dur = ep.get("info",{}).get("duration","")
                                ep_rat = ep.get("info",{}).get("rating","")
                                ep_th  = ep.get("info",{}).get("movie_image",cover)
                                try:    code = f"S{int(s_num):02d}E{int(ep_num):02d}"
                                except: code = f"S{sk}E{ep_num}"
                                fname = f"{sname} {code}" + (f" - {ep_ttl}" if ep_ttl else "")
                                url   = f"{dom}/series/{u}/{p}/{ep_id}.{cont}"
                                extinf = (f'#EXTINF:-1 tvg-id="{ep_id}" tvg-logo="{ep_th}" '
                                          f'group-title="{sname}" tvg-series="{sname}" '
                                          f'tvg-season="{s_num}" tvg-episode="{ep_num}" '
                                          f'tvg-year="{year}" tvg-rating="{ep_rat or rating}" '
                                          f'tvg-director="{director}" tvg-cast="{cast}" '
                                          f'tvg-genre="{genre}" tvg-duration="{ep_dur}" '
                                          f'tvg-backdrop="{bd_url}" tvg-plot="{ep_pl or plot}",{fname}')
                                lines.append({"name":fname,"category":sname,"url":url,"extinf":extinf})
                    except: pass
                    done_count[0] += 1
                    _series_progress["done"] = done_count[0]
                    return idx, lines

                # خيوط ديناميكية لجلب تفاصيل المسلسلات
                with ThreadPoolExecutor(max_workers=min(50, (os.cpu_count() or 4) * 5)) as ex:
                    futs = {ex.submit(fetch_one,(i,s)):i for i,s in enumerate(series_list)}
                    for fut in as_completed(futs):
                        try:
                            idx, lines = fut.result()
                            results[idx] = lines
                        except: pass

                chs = [ch for r in results if r for ch in r]
                ep_count = len(chs)
                _series_progress.update({"finished":True,"channels":chs,"ep_count":ep_count,"series_count":total})
            except Exception as e:
                _series_progress.update({"finished":True,"error":str(e)})

        _web_threading.Thread(target=_do, daemon=True).start()
        return _json({"started": True})

    @_app.route("/api/xtream_series_progress")
    def _xseries_progress():
        # لا نرسل channels في كل استطلاع — فقط عند الانتهاء
        p = dict(_series_progress)
        if not p.get("finished"):
            p.pop("channels", None)
        return _json(p)

    @_app.route("/api/xtream_live", methods=["POST"])
    def _xlive():
        d = _req.get_json()
        dom = d.get("domain","").rstrip("/")
        if not dom.startswith("http"): dom = "http://" + dom
        u,p = d.get("username",""),d.get("password","")
        try:
            base = f"{dom}/player_api.php?username={u}&password={p}"
            cats = {c["category_id"]:c["category_name"] for c in requests.get(base+"&action=get_live_categories",timeout=15,verify=False).json()}
            chs = []
            for s in requests.get(base+"&action=get_live_streams",timeout=30,verify=False).json():
                sid=s.get("stream_id",""); nm=s.get("name","")
                cat=cats.get(str(s.get("category_id","")),s.get("category_name",""))
                logo=s.get("stream_icon","")
                url=f"{dom}/live/{u}/{p}/{sid}.ts"
                chs.append({"name":nm,"category":cat,"url":url,"extinf":f'#EXTINF:-1 tvg-id="{sid}" tvg-logo="{logo}" group-title="{cat}",{nm}'})
            return _json({"channels":chs})
        except Exception as e: return _json({"error":str(e)})

    try: ip = _socket.gethostbyname(_socket.gethostname())
    except: ip = "127.0.0.1"
    print("="*50)
    print("🎬 Opy IPTV V18.9 — وضع الويب")
    print(f"📱 الهاتف:     http://{ip}:5000")
    print(f"💻 الكمبيوتر:  http://localhost:5000")
    print("="*50)
    _app.run(host="0.0.0.0", port=5000, debug=False)




def _run_cloudflare_mode():
    """تشغيل Flask + Cloudflare Tunnel معاً"""
    import subprocess, threading, time, os, platform, urllib.request, re

    # --- 1. إيجاد cloudflared ---
    TERMUX_CF = "/data/data/com.termux/files/usr/bin/cloudflared"
    HOME_CF   = os.path.expanduser("~/cloudflared")

    def find_cf():
        for p in [TERMUX_CF, HOME_CF, "/usr/bin/cloudflared", "/usr/local/bin/cloudflared"]:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
        try:
            r = subprocess.run(["which","cloudflared"], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except: pass
        return None

    cf = find_cf()

    # --- 2. تثبيت إذا غير موجود ---
    if not cf:
        print("⬇  cloudflared غير موجود — جاري التثبيت...")
        # أولاً pkg
        try: subprocess.run(["pkg","install","-y","cloudflared"])
        except: pass
        cf = find_cf()
        # ثانياً تنزيل مباشر
        if not cf:
            arch = platform.machine().lower()
            if "aarch64" in arch or "arm64" in arch:
                link = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
            elif "arm" in arch:
                link = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm"
            else:
                link = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
            print(f"⬇  جاري التنزيل من GitHub...")
            try:
                urllib.request.urlretrieve(link, HOME_CF)
                os.chmod(HOME_CF, 0o755)
                cf = HOME_CF
                print("✅ تم التنزيل")
            except Exception as e:
                print(f"❌ فشل: {e}")
                return
        if not cf:
            print("❌ فشل التثبيت — شغّل يدوياً: pkg install cloudflared")
            return
        print(f"✅ cloudflared جاهز: {cf}")

    # --- 3. أوقف أي عملية على المنفذ 5000 ---
    try:
        subprocess.run(["pkill","-f","flask"], capture_output=True)
        subprocess.run(["fuser","-k","5000/tcp"], capture_output=True)
    except: pass
    time.sleep(1)

    # --- 3. شغّل Flask في الخلفية ---
    threading.Thread(target=_run_web_mode, daemon=True).start()
    time.sleep(3)

    # --- 4. شغّل النفق ---
    print("="*50)
    print("🌍 Opy IPTV V18.9 — وضع Cloudflare Tunnel")
    print(f"   المسار: {cf}")
    print("⏳ جاري إنشاء النفق...")
    print("="*50)

    proc = subprocess.Popen(
        [cf, "tunnel", "--url", "http://localhost:5000"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    for line in proc.stdout:
        print(line, end="")
        m = re.search(r"https://[\w\-]+\.trycloudflare\.com", line)
        if m:
            print("="*50)
            print(f"✅ رابطك العالمي: {m.group()}")
            print("="*50)
    proc.wait()

# ==============================================================
# اختر الوضع عند التشغيل
# ==============================================================
if not _HAS_TK:
    # Termux أو أي بيئة بدون شاشة
    print("="*50)
    print("🎬 Opy IPTV V18.9")
    print("اختر الوضع:")
    print("  1 - ويب (127.0.0.1:5000)")
    print("  2 - عالمي (Cloudflare Tunnel)")
    print("="*50)
    _ch = input("اختيارك (1/2): ").strip()
    if _ch == "2":
        _run_cloudflare_mode()
    else:
        _run_web_mode()
    _sys.exit(0)

_selected_mode = _choose_mode()
if _selected_mode == "web":
    _run_web_mode()
    _sys.exit(0)
if _selected_mode == "cloudflare":
    _run_cloudflare_mode()
    _sys.exit(0)

# إذا اختار محلي — يكمل الكود الأصلي أدناه كما هو تماماً
# ==============================================================

root = tk.Tk()
root.title("🎬 Opy IPTV V18.9")
root.geometry("1200x850")
root.minsize(900, 650)

# ---- شريط العنوان ----
header = tk.Frame(root, bg="#1a1a2e", pady=8)
header.pack(fill="x")
tk.Label(header, text="🎬  Opy IPTV V18.9", bg="#1a1a2e", fg="#e94560",
         font=("Arial", 18, "bold")).pack(side="left", padx=15)
tk.Label(header, text="المدير الشامل لقوائم IPTV", bg="#1a1a2e", fg="#aaaaaa",
         font=("Arial", 10)).pack(side="left")

# ---- Notebook (تبويبات) ----
notebook = ttk.Notebook(root)
# ttk.Notebook = مكون التبويبات (Tabs)
# كل تبويب = Frame مستقل بمحتواه
notebook.pack(fill="both", expand=True, padx=8, pady=5)

tab_editor  = tk.Frame(notebook, bg="#f0f0f0")
tab_xtream  = tk.Frame(notebook, bg="#f0f0f0")
notebook.add(tab_editor, text="  📋 محرر M3U  ")
notebook.add(tab_xtream, text="  📡 Xtream API  ")
# .add(frame, text=...) = إضافة تبويب جديد

# ==============================================================
# التبويب الأول: محرر M3U
# الترتيب الصحيح لـ pack:
#   1. bottom_pane أولاً بـ side="bottom"  ← يُحجز من الأسفل
#   2. mid_pane    ثانياً بـ fill="both"   ← يملأ الباقي
#   3. top_pane    ثالثاً بـ side="top"    ← يُحجز من الأعلى
# هذا يضمن أن bottom_pane لا يختفي أبداً في fullscreen
# ==============================================================

# ---- الخطوة 1: حجز الأسفل أولاً ----
bottom_pane = tk.Frame(tab_editor, bg="#f0f0f0")
bottom_pane.pack(side="bottom", fill="x")

# ---- الخطوة 2: القسم الأوسط يمتد ----
mid_pane = tk.Frame(tab_editor, bg="#f0f0f0")
mid_pane.pack(side="top", fill="both", expand=True)

# ---- الخطوة 3: القسم العلوي ----
top_pane = tk.Frame(tab_editor, bg="#f0f0f0")
top_pane.pack(side="top", fill="x")

# ==============================================================
# محتوى top_pane
# ==============================================================

# ---- صف الملفات ----
frm_files = tk.LabelFrame(top_pane, text=" 📁 الملفات ", bg="#f0f0f0")
frm_files.pack(fill="x", padx=8, pady=5)

tk.Label(frm_files, text="مصدر:", bg="#f0f0f0").grid(row=0, column=0, sticky="e", padx=5, pady=3)
entry_in = tk.Entry(frm_files, width=70)
entry_in.grid(row=0, column=1, padx=5, pady=3)
tk.Button(frm_files, text="📂", command=lambda:(entry_in.delete(0,tk.END), entry_in.insert(0, filedialog.askopenfilename(filetypes=[("M3U","*.m3u"),("All","*.*")])))).grid(row=0, column=2)

tk.Label(frm_files, text="حفظ:", bg="#f0f0f0").grid(row=1, column=0, sticky="e", padx=5, pady=3)
entry_out = tk.Entry(frm_files, width=70)
entry_out.grid(row=1, column=1, padx=5, pady=3)
tk.Button(frm_files, text="💾", command=lambda:(entry_out.delete(0,tk.END), entry_out.insert(0, filedialog.asksaveasfilename(defaultextension=".m3u", filetypes=[("M3U","*.m3u")])))).grid(row=1, column=2)

frm_load_btns = tk.Frame(frm_files, bg="#f0f0f0")
frm_load_btns.grid(row=2, column=0, columnspan=3, pady=5)
tk.Button(frm_load_btns, text="⬇ تحميل", bg="#27ae60", fg="white", width=14, font=("Arial",10,"bold"), command=lambda: load_m3u(entry_in.get())).pack(side="left", padx=6)
tk.Button(frm_load_btns, text="⬆ حفظ",   bg="#2980b9", fg="white", width=14, font=("Arial",10,"bold"), command=lambda: save_m3u(entry_out.get())).pack(side="left", padx=6)

# ---- بحث ----
frm_search = tk.Frame(top_pane, bg="#f0f0f0")
frm_search.pack(fill="x", padx=8, pady=2)
tk.Label(frm_search, text="🔍", bg="#f0f0f0", font=("Arial",12)).pack(side="left")
entry_search = tk.Entry(frm_search, width=60, font=("Arial",10))
entry_search.pack(side="left", padx=5, fill="x", expand=True)
entry_search.bind("<KeyRelease>", lambda e: refresh_listbox(entry_search.get()))
lbl_count = tk.Label(frm_search, text="إجمالي: 0", bg="#f0f0f0", fg="#555")
lbl_count.pack(side="right", padx=10)

# ==============================================================
# محتوى mid_pane — القائمة فقط تمتد
# ==============================================================

frm_list = tk.Frame(mid_pane)
frm_list.pack(fill="both", expand=True, padx=8, pady=3)
sb = tk.Scrollbar(frm_list)
sb.pack(side="right", fill="y")
listbox = tk.Listbox(frm_list, yscrollcommand=sb.set, font=("Consolas",10),
                     selectbackground="#2980b9", selectforeground="white", height=18)
listbox.pack(fill="both", expand=True)
sb.config(command=listbox.yview)
listbox.bind("<<ListboxSelect>>", on_select)

lbl_sel = tk.Label(mid_pane, text="محدد: 0", bg="#f0f0f0", anchor="w")
lbl_sel.pack(fill="x", padx=8)

# ==============================================================
# محتوى bottom_pane — ثابت دائماً لا يختفي في fullscreen
# ==============================================================

# ---- حقول بيانات القناة ----
frm_entry = tk.LabelFrame(bottom_pane, text=" ✏ بيانات القناة ", bg="#f0f0f0")
frm_entry.pack(fill="x", padx=8, pady=3)
tk.Label(frm_entry, text="الاسم:", bg="#f0f0f0").grid(row=0, column=0, sticky="e", padx=5, pady=2)
entry_name = tk.Entry(frm_entry, width=50, font=("Arial",10))
entry_name.grid(row=0, column=1, padx=5, pady=2)
tk.Label(frm_entry, text="التصنيف:", bg="#f0f0f0").grid(row=0, column=2, sticky="e")
entry_cat = tk.Entry(frm_entry, width=30, font=("Arial",10))
entry_cat.grid(row=0, column=3, padx=5, pady=2)
tk.Label(frm_entry, text="الرابط:", bg="#f0f0f0").grid(row=1, column=0, sticky="e", padx=5, pady=2)
entry_url = tk.Entry(frm_entry, width=100, font=("Arial",10))
entry_url.grid(row=1, column=1, columnspan=3, padx=5, pady=2, sticky="ew")

# ---- أزرار الإدارة ----
frm_mgmt = tk.LabelFrame(bottom_pane, text=" 🛠 إدارة ", bg="#f0f0f0")
frm_mgmt.pack(fill="x", padx=8, pady=3)
tk.Button(frm_mgmt, text="➕ إضافة",    bg="#2ecc71", width=12, command=add_channel).pack(side="left", padx=4, pady=4)
tk.Button(frm_mgmt, text="✏ حفظ تعديل", bg="#3498db", fg="white", width=12, command=save_edit).pack(side="left", padx=4, pady=4)
tk.Button(frm_mgmt, text="🗑 حذف",       bg="#e74c3c", fg="white", width=12, command=delete_channels).pack(side="left", padx=4, pady=4)
btn_multi = tk.Button(frm_mgmt, text="☑ اختيار متعدد", width=16, command=toggle_multi)
btn_multi.pack(side="left", padx=4, pady=4)

# ---- استبدال ----
frm_rep = tk.LabelFrame(bottom_pane, text=" 🔄 استبدال في الأسماء ", bg="#f0f0f0")
frm_rep.pack(fill="x", padx=8, pady=3)
tk.Label(frm_rep, text="قديم:", bg="#f0f0f0").pack(side="left", padx=5)
entry_old = tk.Entry(frm_rep, width=22)
entry_old.pack(side="left", padx=4)
tk.Label(frm_rep, text="جديد:", bg="#f0f0f0").pack(side="left")
entry_new = tk.Entry(frm_rep, width=22)
entry_new.pack(side="left", padx=4)
tk.Button(frm_rep, text="🔄 استبدال", bg="#8e44ad", fg="white", command=replace_name).pack(side="left", padx=6)

# ---- فحص ----
frm_check = tk.LabelFrame(bottom_pane, text=" 📡 فحص القنوات ", bg="#f0f0f0")
frm_check.pack(fill="x", padx=8, pady=3)
btn_check = tk.Button(frm_check, text="🔍 فحص ذكي", bg="#f39c12", width=14, command=check_all)
btn_check.pack(side="left", padx=4, pady=4)
tk.Button(frm_check, text="❌ تحديد الميتة",  bg="#c0392b", fg="white", width=15, command=select_offline).pack(side="left", padx=4, pady=4)
tk.Button(frm_check, text="✅ تحديد الشغالة", bg="#27ae60", fg="white", width=15, command=select_online).pack(side="left", padx=4, pady=4)

# ---- إطار التقدم — في bottom_pane لا يختفي أبداً ----
frm_progress = tk.LabelFrame(bottom_pane, text=" 📊 تقدم الفحص ", bg="#f0f0f0")
# لا نستدعي .pack() هنا — يُظهَر فقط داخل check_all

# ---- الصف الأول: النسبة + العداد + الشغّالة + الميتة ----
frm_progress_info = tk.Frame(frm_progress, bg="#f0f0f0")
frm_progress_info.pack(fill="x", padx=6, pady=(4, 2))
# هذا الـ Frame الداخلي يُضاف لـ frm_progress مباشرة (ليس لـ tab_editor)
# لذا لن يظهر إلا عندما يظهر frm_progress نفسه

lbl_progress_pct = tk.Label(
    frm_progress_info, text="0%",
    bg="#f0f0f0", fg="#2c3e50",
    font=("Arial", 11, "bold"), width=6
)
# عداد النسبة المئوية — يتغير من 0% إلى 100%
# width=6 = عرض ثابت يمنع تزحزح العناصر المجاورة عند تغيير الرقم
lbl_progress_pct.pack(side="left", padx=8)

lbl_progress_count = tk.Label(
    frm_progress_info, text="0 / 0",
    bg="#f0f0f0", fg="#555555",
    font=("Arial", 10), width=14
)
# عداد (فُحص / الكلي) — مثال: "247 / 1000"
lbl_progress_count.pack(side="left", padx=4)

tk.Label(frm_progress_info, text="|", bg="#f0f0f0", fg="#cccccc").pack(side="left")
# خط فاصل بصري بين العداد والنتائج

lbl_progress_ok = tk.Label(
    frm_progress_info, text="✅ 0",
    bg="#f0f0f0", fg="#27ae60",
    font=("Arial", 10, "bold"), width=8
)
# عداد الشغّالة — يزيد لحظة بلحظة بلون أخضر
lbl_progress_ok.pack(side="left", padx=6)

lbl_progress_bad = tk.Label(
    frm_progress_info, text="❌ 0",
    bg="#f0f0f0", fg="#e74c3c",
    font=("Arial", 10, "bold"), width=8
)
# عداد الميتة — يزيد لحظة بلحظة بلون أحمر
lbl_progress_bad.pack(side="left", padx=6)

# ---- الصف الثاني: شريط التقدم ----
progress_bar = ttk.Progressbar(frm_progress, mode="determinate")
# mode="determinate" = نسبة معروفة 0 إلى maximum
# يُضاف بـ .pack() داخل check_all فقط عند بدء الفحص
# لا نستدعي .pack() هنا لأننا نريده يظهر ضمن frm_progress عند الفحص

# ==============================================================
# التبويب الثاني: Xtream API
# ==============================================================

# ---- بيانات الاتصال ----
frm_creds = tk.LabelFrame(tab_xtream, text=" 🔐 بيانات الاتصال بخادم Xtream ", bg="#f0f0f0", font=("Arial",10,"bold"))
frm_creds.pack(fill="x", padx=10, pady=8)

# صف Domain
tk.Label(frm_creds, text="Domain / URL:", bg="#f0f0f0", width=14, anchor="e").grid(row=0, column=0, padx=8, pady=6, sticky="e")
entry_domain = tk.Entry(frm_creds, width=55, font=("Arial",11))
entry_domain.grid(row=0, column=1, padx=5, pady=6, sticky="ew")
entry_domain.insert(0, "http://")
# نضع http:// كقيمة ابتدائية لتوجيه المستخدم
tk.Label(frm_creds, text="مثال: http://server.com:8789", bg="#f0f0f0", fg="#888", font=("Arial",9)).grid(row=0, column=2, padx=5)

# صف Username
tk.Label(frm_creds, text="Username:", bg="#f0f0f0", width=14, anchor="e").grid(row=1, column=0, padx=8, pady=6, sticky="e")
entry_uname = tk.Entry(frm_creds, width=35, font=("Arial",11))
entry_uname.grid(row=1, column=1, padx=5, pady=6, sticky="w")

# صف Password
tk.Label(frm_creds, text="Password:", bg="#f0f0f0", width=14, anchor="e").grid(row=2, column=0, padx=8, pady=6, sticky="e")
entry_pass = tk.Entry(frm_creds, width=35, font=("Arial",11), show="●")
# show="●" = يخفي الكتابة ويعرض نقاطاً (مثل حقل كلمة المرور في المتصفحات)
entry_pass.grid(row=2, column=1, padx=5, pady=6, sticky="w")

# زر إظهار/إخفاء كلمة المرور
def toggle_pass_visibility():
    if entry_pass.cget("show") == "●":
        entry_pass.config(show="")
        btn_show_pass.config(text="🙈 إخفاء")
    else:
        entry_pass.config(show="●")
        btn_show_pass.config(text="👁 عرض")

btn_show_pass = tk.Button(frm_creds, text="👁 عرض", width=8, command=toggle_pass_visibility)
btn_show_pass.grid(row=2, column=2, padx=5)

# صف الأزرار
frm_conn_btns = tk.Frame(frm_creds, bg="#f0f0f0")
frm_conn_btns.grid(row=3, column=0, columnspan=3, pady=8)
tk.Button(frm_conn_btns, text="🔗 اختبار الاتصال", bg="#2c3e50", fg="white", width=18,
          font=("Arial",10,"bold"), command=test_xtream_connection).pack(side="left", padx=8)
lbl_xtream_status = tk.Label(frm_conn_btns, text="● غير متصل", fg="#888", bg="#f0f0f0", font=("Arial",10))
lbl_xtream_status.pack(side="left", padx=10)

# ---- أزرار الجلب الثلاثة ----
frm_fetch = tk.LabelFrame(tab_xtream, text=" 📥 جلب المحتوى وحفظه ", bg="#f0f0f0", font=("Arial",10,"bold"))
frm_fetch.pack(fill="x", padx=10, pady=5)

# القنوات الحية
frm_live = tk.Frame(frm_fetch, bg="#f0f0f0", relief="ridge", bd=1)
frm_live.grid(row=0, column=0, padx=12, pady=10, sticky="nsew")
tk.Label(frm_live, text="📺", bg="#f0f0f0", font=("Arial",28)).pack(pady=(10,2))
tk.Label(frm_live, text="القنوات الحية", bg="#f0f0f0", font=("Arial",12,"bold")).pack()
tk.Label(frm_live, text="اسم، تصنيف، شعار، EPG، Catchup", bg="#f0f0f0", fg="#666", font=("Arial",8)).pack(pady=2)
tk.Button(frm_live, text="⬇ جلب وحفظ", bg="#27ae60", fg="white", width=16,
          font=("Arial",10,"bold"), command=fetch_live).pack(pady=(5,10))

# الأفلام
frm_mov = tk.Frame(frm_fetch, bg="#f0f0f0", relief="ridge", bd=1)
frm_mov.grid(row=0, column=1, padx=12, pady=10, sticky="nsew")
tk.Label(frm_mov, text="🎬", bg="#f0f0f0", font=("Arial",28)).pack(pady=(10,2))
tk.Label(frm_mov, text="الأفلام", bg="#f0f0f0", font=("Arial",12,"bold")).pack()
tk.Label(frm_mov, text="اسم، تصنيف، ملصق، تقييم، مخرج، ممثلين، ملخص، تريلر", bg="#f0f0f0", fg="#666", font=("Arial",8)).pack(pady=2)
tk.Button(frm_mov, text="⬇ جلب وحفظ", bg="#8e44ad", fg="white", width=16,
          font=("Arial",10,"bold"), command=fetch_movies).pack(pady=(5,10))

# المسلسلات
frm_ser = tk.Frame(frm_fetch, bg="#f0f0f0", relief="ridge", bd=1)
frm_ser.grid(row=0, column=2, padx=12, pady=10, sticky="nsew")
tk.Label(frm_ser, text="📡", bg="#f0f0f0", font=("Arial",28)).pack(pady=(10,2))
tk.Label(frm_ser, text="المسلسلات", bg="#f0f0f0", font=("Arial",12,"bold")).pack()
tk.Label(frm_ser, text="S01E01، شعار، ملخص، مدة، تقييم، موسم، حلقة", bg="#f0f0f0", fg="#666", font=("Arial",8)).pack(pady=2)
tk.Button(frm_ser, text="⬇ جلب وحفظ", bg="#e67e22", fg="white", width=16,
          font=("Arial",10,"bold"), command=fetch_series).pack(pady=(5,10))

# توسيع الأعمدة بالتساوي
frm_fetch.columnconfigure(0, weight=1)
frm_fetch.columnconfigure(1, weight=1)
frm_fetch.columnconfigure(2, weight=1)
# columnconfigure(col, weight=1) = كل عمود يأخذ نفس المساحة

# ---- شريط تقدم Xtream ----
progress_xtream = ttk.Progressbar(tab_xtream, mode="indeterminate")
# مخفي افتراضياً

# ---- ملاحظات ----
frm_notes = tk.LabelFrame(tab_xtream, text=" ℹ ملاحظات ", bg="#f0f0f0")
frm_notes.pack(fill="x", padx=10, pady=5)
notes_text = (
    "• القنوات الحية: سريعة الجلب — ملف M3U واحد بكل القنوات\n"
    "• الأفلام: متوسطة السرعة — قد تستغرق دقيقة لمكتبات كبيرة\n"
    "• المسلسلات: بطيئة — لأنها تجلب تفاصيل كل مسلسل على حدة (طلب API لكل مسلسل)\n"
    "• كل قسم يُحفظ في ملف M3U منفصل تختار مكانه أنت\n"
    "• بعد الجلب يمكنك تحميل الملف في تبويب المحرر للتعديل عليه"
)
tk.Label(frm_notes, text=notes_text, bg="#f0f0f0", fg="#555", font=("Arial",9), justify="right", anchor="e").pack(fill="x", padx=10, pady=5)

# ==============================================================
# اللقب المتحرك
# ==============================================================

canvas_c = Canvas(root, width=310, height=20, bg=root["bg"], highlightthickness=0)
canvas_c.place(relx=1.0, rely=1.0, x=-10, y=-10, anchor="se")
credit_text = "Opy IPTV V18.9 — by Wael"
canvas_c.create_text(2, 2, text=credit_text, font=("Arial",9,"bold italic"), fill="#444", anchor="nw")
glow_id = canvas_c.create_text(0, 0, text=credit_text, font=("Arial",9,"bold italic"), fill="#aaa", anchor="nw")
color_cycle = itertools.cycle(["#777","#888","#999","#aaa","#bbb","#ccc","#ddd","#eee","#fff","#eee","#ddd","#ccc","#bbb","#aaa"])

def animate():
    canvas_c.itemconfig(glow_id, fill=next(color_cycle))
    root.after(150, animate)

animate()

# ==============================================================
# تشغيل البرنامج
# ==============================================================

root.mainloop()
# حلقة الأحداث الرئيسية — تبقى البرنامج مفتوحاً حتى يغلق المستخدم النافذة
