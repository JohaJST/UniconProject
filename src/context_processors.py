from django.conf import settings

from core.admin import userJust

# Функция interval(request) удалена: слежение за таймаутом сессии дашборда
# (поле User.interval) больше не нужно — эта логика переезжает в Redis
# (ключ user:{user_id}:dashboard_auth со sliding-window TTL 600s),
# реализуется в middleware, а не в context processor.


def APP_NAME(request):
    userJust()
    return {"APP_NAME": settings.APP_NAME}