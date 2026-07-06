[app]
title = Meu Cofre
package.name = meucofre
package.domain = org.meucofre

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 0.1
requirements = python3,kivy==2.3.0,kivymd==1.2.0,requests,beautifulsoup4,pillow,certifi,chardet,idna,urllib3,soupsieve
p4a.branch = develop
cython = 0.29.36

orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
