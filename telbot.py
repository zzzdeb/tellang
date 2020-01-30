#!/usr/bin/env python

import logging

from furigana.furigana import split_furigana
from googletrans import Translator
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (CallbackQueryHandler, CommandHandler, Filters,
                          MessageHandler, Updater)

from config import TOKEN
from game import Game, State
from game_kanji import KanjiGame

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

updater = Updater(TOKEN, use_context=True)


def translate(update, context):
    """
    Docstr
    """
    translator = Translator()
    text = translator.translate(' '.join(context.args), dest='ja').text
    text = text+'\n'
    two_lines = False
    for pair in split_furigana(text):
        if len(pair) == 2:
            two_lines = True
    if two_lines:
        for pair in split_furigana(text):
            if len(pair) == 2:
                kanji, hira = pair
                text = text + "%s(%s)" % (kanji, hira)
            else:
                text = text+pair[0]
    context.bot.send_message(chat_id=update.effective_chat.id, text=text)

#  from telegram import InlineQueryResultArticle, InputTextMessageContent
#  def inline_caps(update, context):
    #  query = update.inline_query.query
    #  if not query:
    #  return
    #  results = list()
    #  results.append(
    #  InlineQueryResultArticle(
    #  id=query.upper(),
    #  title='Caps',
    #  input_message_content=InputTextMessageContent(query.upper())
    #  )
    #  )
    #  context.bot.answer_inline_query(update.inline_query.id, results)

#  from telegram.ext import InlineQueryHandler
#  inline_caps_handler = InlineQueryHandler(inline_caps)
#  dispatcher.add_handler(inline_caps_handler)


def unknown(update, context):
    """
    Docstr
    """
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Sorry, I didn't understand that command.")


BUTTON = {
    'play': '1',
    'vote_next': '2',
    'review_1': '3',
    'review_2': '4',
    'review_3': '5',
    'review_4': '6',
    'play_withanki': '7',
}

play_button = [[InlineKeyboardButton("PLAY?",
                                     callback_data=BUTTON['play']),
               InlineKeyboardButton("PLAY_ANKI?",
                                     callback_data=BUTTON['play_withanki'])]]

play_button_markup = InlineKeyboardMarkup(play_button)

voteNext_button = [[InlineKeyboardButton("Yes",
                                         callback_data=BUTTON["vote_next"])]]
#  context.args
voteNext_button_markup = InlineKeyboardMarkup(voteNext_button)

review_button = [[InlineKeyboardButton("Again",
                                       callback_data=BUTTON["review_1"]),
                  InlineKeyboardButton("Hard",
                                       callback_data=BUTTON["review_2"]), 
                  InlineKeyboardButton("Normal",
                                        callback_data=BUTTON["review_3"]), 
                  InlineKeyboardButton("Easy",
                                        callback_data=BUTTON["review_4"]),
                  ]]
#  context.args
review_button_markup = InlineKeyboardMarkup(review_button)
"""
Basic example for a bot that uses inline keyboards.
"""
GAME = KanjiGame()


def start_timer(context):
    """
    Docstr
    """
    if GAME.state == State.INIT:
        GAME.start()

    context.bot.send_message(chat_id=context.job.context,
                             text='Starting with {} words'.format(len(GAME.all_words)))
    #  updater.job_queue.run_repeating(check, 0.1, context=None, name=None)


def check(context):
    """
    Docstr
    """
    if GAME.state == State.ENDED:
        #  for p, val in GAME.players.items():
        #  try:
        #  port = GAME.players[p]['ankiport']
        #  except KeyError:
        #  continue

        text = GAME.winner_str()+'\n'
        text += 'END'
        context.bot.send_message(chat_id=context.job.context, text=text)

        for p, val in GAME.players.items():
            for cid, word in val['words_to_review'].items():
                context.bot.send_message(chat_id=p, text='{}::{}'.format(
                    GAME.answer_str(word), cid), reply_markup=review_button_markup)
        #  for cid, word in GAME.words_to_review:
            #  context.bot.send_message(chat_id=context.job.context, text='{}::{}'.format(GAME.answer_str(word), cid), reply_markup=review_button_markup)

        GAME.state = State.INIT
        context.job.schedule_removal()


def start(update, context):
    """
    Docstr
    """

    if GAME.state in [State.INIT, State.ENDED]:
        GAME.__init__()
        GAME.context = context
        GAME.update = update
        GAME.updater = updater
        GAME.add_player(update.effective_user)
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=update.effective_user.first_name,
            reply_markup=play_button_markup)
        updater.job_queue.run_once(start_timer, 3,
                                   context=update.message.chat_id, name=None)
        updater.job_queue.run_repeating(check, 0.1,
                                        context=update.message.chat_id,
                                        name='Checker')
    elif GAME.state == State.STARTED:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="Game running")


def answer(update, context):
    """
    Docstr
    """
    GAME.answer(update.effective_user.id, ' '.join(context.args))
    if GAME.state == State.INIT:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=GAME.winner_str())

        return 1


def end_game(update, context, winner_announce=False):
    """
    Docstr
    """
    text = ''
    if winner_announce:
        text += GAME.winner_str() + '🎆🎆🎆\n'
    text += 'END'
    GAME.end_game()
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=text)
    return 0


def announce_winner(update, context):
    """
    Docstr
    """
    context.bot.send_message(update.effective_chat.id, text=GAME.winner_str())


def vote_next(update, context):
    """
    Docstr
    """
    text = GAME.answer_str()
    if not GAME.vote_next(update.effective_user.id):
        context.bot.send_message(
            chat_id=update.effective_chat.id, text='Next?',
            reply_markup=voteNext_button_markup)
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id, text=text)
        if GAME.state == State.ENDED:
            announce_winner(update, context)


def button(update, context):
    """
    Docstr
    """
    query = update.callback_query
    if query.data == BUTTON["play"]:
        if not GAME.add_player(update.effective_user, with_anki=False):
            query.edit_message_text(text='{}\n{}'.format(
                query.message.text, update.effective_user.first_name), reply_markup=play_button_markup)
    elif query.data == BUTTON["play_withanki"]:
        if not GAME.add_player(update.effective_user, with_anki=True):
            query.edit_message_text(text='{}\n{}'.format(
                query.message.text, update.effective_user.first_name), reply_markup=play_button_markup)
    elif query.data == BUTTON["vote_next"]:
        if GAME.vote_next(update.effective_user.id) == 0:
            query.edit_message_text(text='{}\n{}'.format(
                query.message.text, update.effective_user.first_name), reply_markup=play_button_markup)
        else:
            query.edit_message_text(text='Next:')
    elif query.data == BUTTON["review_1"]:
        GAME.anki_answer(update.effective_user.id,
                         int(query.message.text.split('::')[1]), ease=1)
        query.edit_message_text(text='_{}_'.format(
            query.message.text), parse_mode=telegram.ParseMode.MARKDOWN)
    elif query.data == BUTTON["review_2"]:
        GAME.anki_answer(update.effective_user.id,
                         int(query.message.text.split('::')[1]), ease=2)
        query.edit_message_text(
            text='*{}*'.format(query.message.text), parse_mode=telegram.ParseMode.MARKDOWN)
    elif query.data == BUTTON["review_3"]:
        GAME.anki_answer(update.effective_user.id,
                         int(query.message.text.split('::')[1]), ease=3)
        query.edit_message_text(
            text='*{}*'.format(query.message.text), parse_mode=telegram.ParseMode.MARKDOWN)
    elif query.data == BUTTON["review_4"]:
        GAME.anki_answer(update.effective_user.id,
                         int(query.message.text.split('::')[1]), ease=4)
        query.edit_message_text(
            text='*{}*'.format(query.message.text), parse_mode=telegram.ParseMode.MARKDOWN)


def bothelp(update, context):
    """
    Docstr
    """
    update.message.reply_text("Use /start to test this bot.")


def error(update, context):
    """Log Errors caused by Updates."""
    LOGGER.warning('Update "%s" caused error "%s"', update, context.error)


def echo(context):
    """
    Docstr
    """
    print(context.user_data)


def status(update, context):
    """
    Docstr
    """
    update.message.reply_text(str(update)+'\n'+str(context))


def main():
    """
    Docstr
    """
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater.dispatcher.add_handler(CommandHandler('start', start))
    updater.dispatcher.add_handler(CallbackQueryHandler(button))
    updater.dispatcher.add_handler(CommandHandler('help', bothelp))
    updater.dispatcher.add_handler(MessageHandler(Filters.text, translate))
    updater.dispatcher.add_handler(CommandHandler('status', status))
    updater.dispatcher.add_handler(CommandHandler('t', translate))
    updater.dispatcher.add_handler(CommandHandler('p', start))
    updater.dispatcher.add_handler(CommandHandler('q', end_game))
    updater.dispatcher.add_handler(CommandHandler('n', vote_next))
    updater.dispatcher.add_handler(CommandHandler('a', answer))

    updater.dispatcher.add_error_handler(error)

    updater.dispatcher.add_handler(MessageHandler(Filters.command, unknown))
    # Start the Bot
    updater.start_polling()

    # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()


if __name__ == '__main__':
    main()
