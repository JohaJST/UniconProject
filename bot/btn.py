from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from core.models import User, ClassRooms

def key_btn(type, ctg=None):
    btn = []
    if type == 'contact':
        btn = [
            [KeyboardButton("Отправьте номер", request_contact=True)]
        ]
    elif type == "menu":
        btn = [
            [KeyboardButton("Решённые тесты")],
        ]
    elif type == "classrooms":
        classrooms = ClassRooms.objects.all()
        for i in range(1, len(classrooms), 2):
            btn += [KeyboardButton(classrooms[i - 1].name), KeyboardButton(classrooms[i].name)],

        if not len(classrooms) % 2 == 0:
            btn.append(
                [KeyboardButton(classrooms[len(classrooms)-1].name)]
            )
    elif type == "user":

        classrooms = User.objects.filter(classroom=ctg)
        for i in range(1, len(classrooms), 2):
            btn += [KeyboardButton(classrooms[i - 1].full_name()), KeyboardButton(classrooms[i].full_name())],
        if not len(classrooms) % 2 == 0:
            btn.append(
                [KeyboardButton(classrooms[len(classrooms)-1].full_name())]
            )
    # print(btn)
    return ReplyKeyboardMarkup(btn, resize_keyboard=True)
