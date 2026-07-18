[app]
title = AlbionHelper
package.name = albionhelper
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json
version = 0.1
requirements = python3,kivy,opencv,numpy,requests
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,WAKE_LOCK,ACCESS_WIFI_STATE,CHANGE_WIFI_STATE
android.api = 31
android.minapi = 21
android.ndk = 25b
android.sdk = 24
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master

[buildozer]
log_level = 2
warn_on_root = 1
