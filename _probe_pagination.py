# -*- coding: utf-8 -*-
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.settings")
import django
django.setup()

from django.test import Client
from core.auth_jwt.services import AuthRedisService

c = Client(raise_request_exception=False)
c.post("/login/", {"user": "8"})
AuthRedisService.authorize_dashboard(8)
r = c.get("/dashboard/list/selfresult/")
print("selfresult list ->", r.status_code)
r2 = c.get("/dashboard/list/question/")
print("question list ->", r2.status_code)
