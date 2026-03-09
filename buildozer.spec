[app]
title = Opy IPTV
package.name = opyiptv
package.domain = org.wael
source.dir = .
source.include_exts = py
version = 18.9
requirements = python3,flask,requests,urllib3
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a
p4a.bootstrap = webview
log_level = 2

[buildozer]
log_level = 2
