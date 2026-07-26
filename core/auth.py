"""
core/auth.py
──────────────
Вход и выход пользователя на JWT-аутентификации.

Django session-логин (login/logout/authenticate) больше не используется —
аутентификация запроса выполняется JWTAuthenticationMiddleware по
access_token cookie (см. core/auth_jwt/middleware.py), а не по
django.contrib.sessions.
"""
import hashlib
import time
import uuid

import jwt
from django.conf import settings
from django.shortcuts import redirect, render

from core.models import ClassRooms, User
from core.auth_jwt.services import AuthRedisService
from core.auth_jwt.tokens import generate_tokens


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

        # ── Новая JWT-сессия: генерируем идентификаторы устройства и семьи ──
        # device_id — новое устройство/сессия при каждом логине;
        # family_id — новая цепочка ротации refresh-токена для этой сессии.
        device_id = uuid.uuid4().hex
        family_id = uuid.uuid4().hex

        # ua_hash: не храним сырой User-Agent, только его хэш — достаточно,
        # чтобы заметить смену браузера/устройства, но не тратим место в Redis.
        ua_raw = requests.META.get("HTTP_USER_AGENT", "")
        ua_hash = hashlib.sha256(ua_raw.encode("utf-8")).hexdigest()

        # ip_subnet: округляем IPv4 до /24, чтобы не разлогинивать пользователя
        # при смене IP внутри той же подсети (мобильный оператор, NAT и т.п.);
        # для нестандартного формата (IPv6, пусто) — берём как есть.
        ip_raw = requests.META.get("REMOTE_ADDR", "")
        ip_parts = ip_raw.split(".")
        ip_subnet = ".".join(ip_parts[:3]) + ".0/24" if len(ip_parts) == 4 else ip_raw

        AuthRedisService.set_active_session(
            user_id=user.id,
            device_id=device_id,
            ua_hash=ua_hash,
            ip_subnet=ip_subnet,
        )

        tokens = generate_tokens(user_id=user.id, device_id=device_id, family_id=family_id)

        # Успешный логин — сбрасываем счётчик неудачных попыток юзера.
        AuthRedisService.clear_login_attempts(user.id)

        # Как и в старом коде: админов сразу отправляем на форму пароля
        # дашборда, остальных — на главную.
        response = redirect("lock") if user.is_admin else redirect("home")

        # Флаги cookie и TTL берём из settings (Промпт 1) — они равны
        # httponly=True, secure=True, samesite='Lax', как того требует
        # Shared Context, но заданы централизованно, а не хардкодом здесь.
        response.set_cookie(
            settings.JWT_ACCESS_COOKIE_NAME,
            tokens["access_token"],
            max_age=settings.JWT_ACCESS_TOKEN_TTL,
            httponly=settings.JWT_COOKIE_HTTPONLY,
            secure=settings.JWT_COOKIE_SECURE,
            samesite=settings.JWT_COOKIE_SAMESITE,
        )
        response.set_cookie(
            settings.JWT_REFRESH_COOKIE_NAME,
            tokens["refresh_token"],
            max_age=settings.JWT_REFRESH_TOKEN_TTL,
            httponly=settings.JWT_COOKIE_HTTPONLY,
            secure=settings.JWT_COOKIE_SECURE,
            samesite=settings.JWT_COOKIE_SAMESITE,
        )

        return response

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


def sign_out(request):
    """
    Логаут: отзывает текущий access-токен по jti, удаляет активную сессию
    устройства пользователя в Redis и стирает обе JWT-куки.

    @login_required убран вместе с импортом: стандартная Django
    session-аутентификация не используется — на защищённые пути запрос
    вообще не дойдёт без валидного access_token, это уже гарантирует
    JWTAuthenticationMiddleware (см. core/auth_jwt/middleware.py).
    """
    access_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME)

    if access_token:
        try:
            # verify_signature=False: на логауте токен вполне может быть уже
            # просроченным (exp в прошлом) — это не повод падать с ошибкой,
            # нам нужен только payload (jti, sub), а не подтверждение подлинности.
            payload = jwt.decode(access_token, options={"verify_signature": False})
        except jwt.DecodeError:
            payload = {}

        jti = payload.get("jti")
        exp = payload.get("exp")

        if jti:
            # Оставшийся TTL — сколько ключу token:revoked:{jti} жить в Redis,
            # чтобы запись не пережила сам токен. Если exp уже в прошлом —
            # ставим минимальный TTL (1s), лишь бы не хранить ключ вечно.
            remaining_ttl = max(int(exp - time.time()), 1) if exp else settings.JWT_ACCESS_TOKEN_TTL
            AuthRedisService.revoke_token(jti, remaining_ttl)

        user_id = payload.get("sub")
        if user_id is not None:
            # Удаляем запись об активном устройстве — старые ещё не истёкшие
            # токены (например, refresh) перестанут проходить validate_session.
            AuthRedisService.clear_active_session(user_id)

    """
    core/auth.py
    ──────────────
    Вход и выход пользователя на JWT-аутентификации.
    
    Django session-логин (login/logout/authenticate) больше не используется —
    аутентификация запроса выполняется JWTAuthenticationMiddleware по
    access_token cookie (см. core/auth_jwt/middleware.py), а не по
    django.contrib.sessions.
    """
    import hashlib
    import time
    import uuid
    
    import jwt
    from django.conf import settings
    from django.shortcuts import redirect, render
    
    from core.models import ClassRooms, User
    from core.auth_jwt.exceptions import TokenExpired, TokenInvalid
    from core.auth_jwt.services import AuthRedisService
    from core.auth_jwt.tokens import decode_token, generate_tokens
    
    
    def _redirect_to_login_clearing_cookies():
        """
        Общий хелпер для этого файла: редирект на login с удалением обеих
        JWT-кук. Не переиспользует одноимённый метод из middleware.py,
        чтобы не тянуть зависимость controllers -> middleware в обе стороны —
        логика тривиальна и дублирование здесь дешевле лишней связанности.
        """
        response = redirect("login")
        response.delete_cookie(settings.JWT_ACCESS_COOKIE_NAME)
        response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME)
        return response
    
    
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
    
            # ── Новая JWT-сессия: генерируем идентификаторы устройства и семьи ──
            # device_id — новое устройство/сессия при каждом логине;
            # family_id — новая цепочка ротации refresh-токена для этой сессии.
            device_id = uuid.uuid4().hex
            family_id = uuid.uuid4().hex
    
            # ua_hash: не храним сырой User-Agent, только его хэш — достаточно,
            # чтобы заметить смену браузера/устройства, но не тратим место в Redis.
            ua_raw = requests.META.get("HTTP_USER_AGENT", "")
            ua_hash = hashlib.sha256(ua_raw.encode("utf-8")).hexdigest()
    
            # ip_subnet: округляем IPv4 до /24, чтобы не разлогинивать пользователя
            # при смене IP внутри той же подсети (мобильный оператор, NAT и т.п.);
            # для нестандартного формата (IPv6, пусто) — берём как есть.
            ip_raw = requests.META.get("REMOTE_ADDR", "")
            ip_parts = ip_raw.split(".")
            ip_subnet = ".".join(ip_parts[:3]) + ".0/24" if len(ip_parts) == 4 else ip_raw
    
            AuthRedisService.set_active_session(
                user_id=user.id,
                device_id=device_id,
                ua_hash=ua_hash,
                ip_subnet=ip_subnet,
            )
    
            tokens = generate_tokens(user_id=user.id, device_id=device_id, family_id=family_id)
    
            # Успешный логин — сбрасываем счётчик неудачных попыток юзера.
            AuthRedisService.clear_login_attempts(user.id)
    
            # Как и в старом коде: админов сразу отправляем на форму пароля
            # дашборда, остальных — на главную.
            response = redirect("lock") if user.is_admin else redirect("home")
    
            # Флаги cookie и TTL берём из settings (Промпт 1) — они равны
            # httponly=True, secure=True, samesite='Lax', как того требует
            # Shared Context, но заданы централизованно, а не хардкодом здесь.
            response.set_cookie(
                settings.JWT_ACCESS_COOKIE_NAME,
                tokens["access_token"],
                max_age=settings.JWT_ACCESS_TOKEN_TTL,
                httponly=settings.JWT_COOKIE_HTTPONLY,
                secure=settings.JWT_COOKIE_SECURE,
                samesite=settings.JWT_COOKIE_SAMESITE,
            )
            response.set_cookie(
                settings.JWT_REFRESH_COOKIE_NAME,
                tokens["refresh_token"],
                max_age=settings.JWT_REFRESH_TOKEN_TTL,
                httponly=settings.JWT_COOKIE_HTTPONLY,
                secure=settings.JWT_COOKIE_SECURE,
                samesite=settings.JWT_COOKIE_SAMESITE,
            )
    
            return response
    
        return render(requests, 'pages/auth/login.html', ctx)
    
    
    def refresh_token_view(request):
        """
        Ротация access/refresh токенов по действующему refresh_token cookie.
    
        Вызывается, когда JWTAuthenticationMiddleware перенаправляет сюда после
        истечения access-токена (see core/auth_jwt/middleware.py, ?next=...).
    
        Reuse-detection: если хэш предъявленного refresh-токена не совпадает
        с current_token_hash, записанным в rt_family (или семья уже помечена
        compromised) — это означает, что кто-то предъявил уже заротированный
        (использованный ранее) refresh-токен, т.е. токен был скомпрометирован
        (украден). В этом случае вся семья и вся сессия пользователя убиваются.
        """
        refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not refresh_token:
            return _redirect_to_login_clearing_cookies()
    
        try:
            payload = decode_token(refresh_token, token_type="refresh")
        except (TokenExpired, TokenInvalid):
            return _redirect_to_login_clearing_cookies()
    
        user_id = payload.get("sub")
        device_id = payload.get("device_id")
        family_id = payload.get("family_id")
    
        family = AuthRedisService.get_family(family_id)
        current_hash = family.get("current_token_hash") if family else None
        is_compromised = family.get("compromised", False) if family else True
    
        presented_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    
        if is_compromised or presented_hash != current_hash:
            # Reuse Attack (или семья потеряна/протухла в Redis) — убиваем всю
            # сессию пользователя, а не только эту семью.
            AuthRedisService.mark_family_compromised(family_id)
            AuthRedisService.kick_user(user_id)
            return _redirect_to_login_clearing_cookies()
    
        # ── Всё совпало — ротация: новая пара токенов, старый device_id/family_id ──
        new_tokens = generate_tokens(user_id=user_id, device_id=device_id, family_id=family_id)
        new_refresh_hash = hashlib.sha256(new_tokens["refresh_token"].encode("utf-8")).hexdigest()
        AuthRedisService.rotate_refresh_family(family_id, new_refresh_hash)
    
        response = redirect(request.GET.get('next', 'home'))
    
        response.set_cookie(
            settings.JWT_ACCESS_COOKIE_NAME,
            new_tokens["access_token"],
            max_age=settings.JWT_ACCESS_TOKEN_TTL,
            httponly=settings.JWT_COOKIE_HTTPONLY,
            secure=settings.JWT_COOKIE_SECURE,
            samesite=settings.JWT_COOKIE_SAMESITE,
        )
        response.set_cookie(
            settings.JWT_REFRESH_COOKIE_NAME,
            new_tokens["refresh_token"],
            max_age=settings.JWT_REFRESH_TOKEN_TTL,
            httponly=settings.JWT_COOKIE_HTTPONLY,
            secure=settings.JWT_COOKIE_SECURE,
            samesite=settings.JWT_COOKIE_SAMESITE,
        )
    
        return response
    
    
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
    
    
    def sign_out(request):
        """
        Логаут: отзывает текущий access-токен по jti, удаляет активную сессию
        устройства пользователя в Redis и стирает обе JWT-куки.
    
        @login_required убран вместе с импортом: стандартная Django
        session-аутентификация не используется — на защищённые пути запрос
        вообще не дойдёт без валидного access_token, это уже гарантирует
        JWTAuthenticationMiddleware (см. core/auth_jwt/middleware.py).
        """
        access_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME)
    
        if access_token:
            try:
                # verify_signature=False: на логауте токен вполне может быть уже
                # просроченным (exp в прошлом) — это не повод падать с ошибкой,
                # нам нужен только payload (jti, sub), а не подтверждение подлинности.
                payload = jwt.decode(access_token, options={"verify_signature": False})
            except jwt.DecodeError:
                payload = {}
    
            jti = payload.get("jti")
            exp = payload.get("exp")
    
            if jti:
                # Оставшийся TTL — сколько ключу token:revoked:{jti} жить в Redis,
                # чтобы запись не пережила сам токен. Если exp уже в прошлом —
                # ставим минимальный TTL (1s), лишь бы не хранить ключ вечно.
                remaining_ttl = max(int(exp - time.time()), 1) if exp else settings.JWT_ACCESS_TOKEN_TTL
                AuthRedisService.revoke_token(jti, remaining_ttl)
    
            user_id = payload.get("sub")
            if user_id is not None:
                # Удаляем запись об активном устройстве — старые ещё не истёкшие
                # токены (например, refresh) перестанут проходить validate_session.
                AuthRedisService.clear_active_session(user_id)
    
        response = redirect("login")
        response.delete_cookie(settings.JWT_ACCESS_COOKIE_NAME)
        response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME)
        return response = redirect("login")
    response.delete_cookie(settings.JWT_ACCESS_COOKIE_NAME)
    response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME)
    return response