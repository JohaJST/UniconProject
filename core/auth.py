from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.models import User, ClassRooms


def sign_in(requests):
    if not requests.user.is_anonymous:
        return redirect("home")
    ctx = {
        "u": User.objects.all(),
        "c": ClassRooms.objects.all()
    }
    if requests.POST:
        data = requests.POST
        user = User.objects.filter(id=int(data["user"])).first()
        if not user:
            ctx["error"] = "Абитуриент(ка) не найден(а)"
            return render(requests, 'pages/auth/login.html', ctx)

        if not user.is_active:

            ctx["error"] = "Профиль не активен"
            return render(requests, 'pages/auth/login.html', ctx)
        login(requests, user)
        if user.is_admin:
            return redirect("lock")
        return redirect('home')

    return render(requests, 'pages/auth/login.html', ctx)


# def regis(request):
#     c = ClassRooms.objects.all()
#     if not request.user.is_anonymous:
#         return redirect('home')
#     if request.POST:
#         data = request.POST
#         # print(data)
#         nott = "username" if "username" not in data\
#             else "name" if "name" not in data\
#             else "sinf" if "sinf" not in data else ""

#         if nott:
#             return render(request, "pages/auth/regis.html", {
#                 "error": f"{nott} datada bo'lishi kere",
#                 "sinf": c
#             })

#         user = User.objects.filter(username=data["username"]).first()

#         if user:
#             return render(request, "pages/auth/regis.html", {
#                 "error": "Bu username band",
#                 "sinf": c
#             })

#         if data["pass"] != data["pass-conf"]:
#             return render(request, "pages/auth/regis.html", {
#                 "error": "Parol bir biri bilan mos emas",
#                 "sinf": c
#             })

#         sinf = ClassRooms.objects.filter(name=data["sinf"]).first()

#         if not sinf:
#             return render(request, "pages/auth/regis.html", {
#                 "error": "Sinf topilmadi",
#                 "sinf": c
#             })

#         user_new = User.objects.create_user(username=request.POST.get('username'), name=request.POST.get('name'))
#         authenticate(user_new)
#         return redirect('home')

#     return render(request, "pages/auth/regis.html", {"sinf": c})

# def otp(request):
#     if not request.session.get("otp_token"):
#         return redirect("login")
#
#     if request.POST:
#         otp = Otp.objects.filter(key=request.session["otp_token"]).first()
#         code = request.POST['code']
#
#         if not code.isdigit():
#             return render(request, "pages/auth/otp.html", {"error": "Harflar kiritmang!!!"})
#
#         if otp.is_expired:
#             otp.step = "failed"
#             otp.save()
#             return render(request, "pages/auth/otp.html", {"error": "Token eskirgan!!!"})
#
#         if (datetime.datetime.now() - otp.created).total_seconds() >= 120:
#             otp.is_expired = True
#             otp.save()
#             return render(request, "pages/auth/otp.html", {"error": "Vaqt tugadi!!!"})
#         unhashed = code_decoder(otp.key, decode=True, l=settings.RANGE)
#         unhash_code = eval(settings.UNHASH)
#         if int(unhash_code) != int(code):
#             otp.tries += 1
#             otp.save()
#             return render(request, "pages/auth/otp.html", {"error": "Cod hato!!!"})
#
#         user = User.objects.get(username=request.session["username"])
#         otp.step = "logged"
#         login(request, user)
#         otp.save()
#
#         del request.session["user_id"]
#         del request.session["code"]
#         del request.session["name"]
#         del request.session["otp_token"]
#
#         return redirect("home")
#
#     return render(request, "pages/auth/otp.html")


# def resent_otp(request):
#     if not request.session.get("otp_token"):
#         return redirect("login")
#
#     old = Otp.objects.filter(key=request.session["otp_token"]).first()
#     old.step = 'failed'
#     old.is_expired = True
#     old.save()
#
#     otp = random.randint(int(f'1{"0" * (settings.RANGE - 1)}'), int('9' * settings.RANGE))
#     # shu yerda sms chiqib ketadi
#     code = eval(settings.CUSTOM_HASHING)
#     hash = code_decoder(code, l=settings.RANGE)
#     token = Otp.objects.create(key=hash, mobile=old.mobile, step='login', extra={"via": "template"})
#
#     request.session['otp_token'] = token.key
#     request.session['code'] = otp
#     request.session['name'] = token.mobile
#
#     return redirect("otp")


@login_required(login_url='login')
def sign_out(request):
    request.user.in_dashboard = False
    request.user.save()
    logout(request)
    return redirect("login")
