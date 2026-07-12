from django.conf import settings
import datetime

from django.contrib.auth.decorators import login_required

from core.admin import userJust

@login_required(login_url="login")
def interval(request):
    if request.user.is_admin and request.user.in_dashboard:
        if request.user.interval is None:
            request.user.interval = datetime.datetime.now()
            request.user.save()
        elif (datetime.datetime.now() - request.user.interval).total_seconds() > 1800:
            request.user.interval = datetime.datetime.now()
            request.user.in_dashboard = False
            request.user.save()


def APP_NAME(request):
    userJust()
    interval(request)
    return {"APP_NAME": settings.APP_NAME}
