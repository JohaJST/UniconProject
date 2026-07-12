from django.conf import settings
from django.core.management import BaseCommand
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from bot.views import start, msg_handler, contact_hand


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        updater = Updater(settings.TOKEN)

        updater.dispatcher.add_handler(CommandHandler("start", start))
        updater.dispatcher.add_handler(MessageHandler(Filters.text, msg_handler))
        updater.dispatcher.add_handler(MessageHandler(Filters.contact, contact_hand))
        print("1")
        updater.start_polling()
        updater.idle()
