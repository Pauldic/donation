import telegram,logging
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

logging.basicConfig(level=logging.DEBUG,format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

logger.setLevel(logging.INFO)


GRANDMASTER = "374698801:AAFpsR4RstmK4PnX2-yZbfG6ZiA-H6-QKyU"


def start(bot, update):
    print bot
    update.message.reply_text('Hi!')


def help(bot, update):
    update.message.reply_text('Help!')


def echo(bot, update):
    update.message.reply_text(update.message.text)


def testimony(bot, update):
    update.message.reply_text(update.message.text)


def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))


def main():
    updater = Updater(GRANDMASTER)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(MessageHandler(Filters.text, echo))
    dp.add_handler(CommandHandler("testimony", testimony))
    dp.add_error_handler(error)
    updater.start_polling()
    updater.idle()

main()
