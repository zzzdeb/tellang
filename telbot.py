#!/usr/bin/env python

from config import ANKIPORTS
from game import invoke
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
from game_4000 import English4000Game

import xml.etree.ElementTree as ET
import base64

from io import BytesIO
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

updater = Updater(TOKEN, use_context=True)


def kanji_lookup_str_image(text):
    port = '8766'
    res = []
    for kanji in text:
        nids = invoke('findNotes', port,
                      query='"deck:Nihongo::01 NihongoShark.com: Kanji - with mn" kanji:{}'.format(kanji))
        if len(nids)!=1:
            continue

        for note_info in invoke('notesInfo', port, notes=nids):
            look = ['kanji', 'keyword', 'constituent', 'myStory',
                    'heisigStory', 'koohiiStory1', 'onYomi', 'kunYomi']
            #  media = ['strokeDiagram']
            text = '\n'.join('<b>{}</b>: {}'.format(
                val, note_info['fields'][val]['value']) for val in filter(lambda x: len(note_info['fields'][x]['value']) > 0, look))

            root = ET.fromstring(note_info['fields']['strokeDiagram']['value'])
            print(root.get('src'))
            encoded_image = invoke('retrieveMediaFile',
                                   port, filename=str(root.get('src')))
            #  image = base64.b64decode(encoded_image)
            fh = BytesIO(base64.b64decode(encoded_image))
            res.append((text, fh))

    return res


def kanji_lookup(update, context):
    """
    Docstr
    """
    pairs = kanji_lookup_str_image(update.message.text)

    for text, fh in pairs:
        context.bot.send_photo(
            chat_id=update.effective_chat.id, message='test', photo=fh)

        context.bot.send_message(
            chat_id=update.effective_chat.id, text=text, parse_mode=telegram.ParseMode.HTML)


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


def unknown(update, context):
    """
    Docstr
    """
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Sorry, I didn't understand that command.")


class TelLang(object):

    """Docstring for TelLang. """

    def __init__(self):
        """TODO: to be defined. """
        self.game = Game()
        self.updater = Updater(TOKEN, use_context=True)

        self.BUTTON = {
            'play': '1',
            'vote_next': '2',
            'review_1': '3',
            'review_2': '4',
            'review_3': '5',
            'review_4': '6',
            'play_withanki': '7',
            'kanji_info': '8',
        }

        play_button = [[InlineKeyboardButton("PLAY?",
                                             callback_data=self.BUTTON['play']),
                        InlineKeyboardButton("PLAY_ANKI?",
                                             callback_data=self.BUTTON['play_withanki'])]]

        self.play_button_markup = InlineKeyboardMarkup(play_button)

        voteNext_button = [[InlineKeyboardButton("Yes",
                                                 callback_data=self.BUTTON["vote_next"])]]
        #  context.args
        self.voteNext_button_markup = InlineKeyboardMarkup(voteNext_button)

        self.review_button = [[InlineKeyboardButton("Again",
                                                    callback_data=self.BUTTON["review_1"]),
                               InlineKeyboardButton("Hard",
                                                    callback_data=self.BUTTON["review_2"]),
                               InlineKeyboardButton("Normal",
                                                    callback_data=self.BUTTON["review_3"]),
                               InlineKeyboardButton("Easy",
                                                    callback_data=self.BUTTON["review_4"]),
                               ]]

        self.kanji_info_button = InlineKeyboardButton("KanjiInfo",
                                                      callback_data=self.BUTTON["kanji_info"])
        #  context.args
        self.review_button_markup = InlineKeyboardMarkup(self.review_button)

    def start_timer(self, context):
        """
        Docstr
        """
        if self.game.state == State.INIT:
            context.bot.send_message(chat_id=context.job.context,
                                     text='Preparing ...')
            self.game.start()

        context.bot.send_message(chat_id=context.job.context,
                                 text='Starting with {} words'.format(len(self.game.all_words)))
        #  updater.job_queue.run_repeating(check, 0.1, context=None, name=None)

    def check(self, context):
        """
        Docstr
        """
        if self.game.state == State.ENDED:
            self.game.state = State.INIT
            #  for p, val in self.game.players.items():
            #  try:
            #  port = self.game.players[p]['ankiport']
            #  except KeyError:
            #  continue

            text = self.game.winner_str()+'\n'
            text += 'END'
            context.bot.send_message(chat_id=context.job.context, text=text)

            for p, val in self.game.players.items():
                for cid, word in val['words_to_review'].items():
                    markup = ''
                    buttons = self.game.all_words[word]['answerButtons']
                    if buttons == 2:
                        markup = InlineKeyboardMarkup(
                            [self.review_button[0][:2] +
                             [self.kanji_info_button]])
                    elif buttons == 3:
                        markup = InlineKeyboardMarkup(
                            [self.review_button[0][:3] +
                             [self.kanji_info_button]])
                    elif buttons == 4:
                        markup = InlineKeyboardMarkup(
                            [self.review_button[0][:4]+[self.kanji_info_button]])

                    context.bot.send_message(chat_id=p, text='{}::{}'.format(
                        self.game.answer_str(word), cid), reply_markup=markup)

            #  for cid, word in self.game.words_to_review:
                #  context.bot.send_message(chat_id=context.job.context, text='{}::{}'.format(self.game.answer_str(word), cid), reply_markup=review_button_markup)

            context.job.schedule_removal()

    def start(self, update, context):
        """
        Docstr
        """

        if self.game.state in [State.INIT, State.ENDED]:
            self.game = Game()
            if len(context.args) > 0:
                if context.args[0] == 'kanji':
                    self.game = KanjiGame()
                elif context.args[0] == 'eng':
                    self.game = English4000Game()
            self.game.context = context
            self.game.update = update
            self.game.updater = updater
            self.game.add_player(update.effective_user)
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text='{}\n{}'.format(self.game.deckname,
                                     update.effective_user.first_name),
                reply_markup=self.play_button_markup)
            updater.job_queue.run_once(self.start_timer, 3,
                                       context=update.message.chat_id, name=None)
            updater.job_queue.run_repeating(self.check, 0.1,
                                            context=update.message.chat_id,
                                            name='Checker')
        elif self.game.state == State.STARTED:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Game running")

    def answer(self, update, context):
        """
        Docstr
        """
        self.game.answer(update.effective_user.id, ' '.join(context.args))
        if self.game.state == State.INIT:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=self.game.winner_str())

            return 1

    def end_game(self, update, context, winner_announce=False):
        """
        Docstr
        """
        text = ''
        if winner_announce:
            text += self.game.winner_str() + '🎆🎆🎆\n'
        text += 'END'
        self.game.end_game()
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=text)
        return 0

    def announce_winner(self, update, context):
        """
        Docstr
        """
        context.bot.send_message(
            update.effective_chat.id, text=self.game.winner_str())

    def vote_next(self, update, context):
        """
        Docstr
        """
        text = self.game.answer_str()
        if not self.game.vote_next(update.effective_user.id):
            context.bot.send_message(
                chat_id=update.effective_chat.id, text='Next?',
                reply_markup=self.voteNext_button_markup)
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id, text=text)
            if self.game.state == State.ENDED:
                self.announce_winner(update, context)

    def button(self, update, context):
        """
        Docstr
        """
        query = update.callback_query
        if query.data == self.BUTTON["play"]:
            if not self.game.add_player(update.effective_user, with_anki=False) and self.game.state == State.INIT:
                query.edit_message_text(text='{}\n{}'.format(
                    query.message.text, update.effective_user.first_name), reply_markup=self.play_button_markup)
        elif query.data == self.BUTTON["play_withanki"]:
            if not self.game.add_player(update.effective_user, with_anki=True) and self.game.state == State.INIT:
                query.edit_message_text(text='{}\n{}'.format(
                    query.message.text, update.effective_user.first_name), reply_markup=self.play_button_markup)
        elif query.data == self.BUTTON["vote_next"]:
            if self.game.vote_next(update.effective_user.id) == 0:
                query.edit_message_text(text='{}\n{}'.format(
                    query.message.text, update.effective_user.first_name), reply_markup=self.play_button_markup)
            else:
                query.edit_message_text(text='Next:')
        elif query.data == self.BUTTON["review_1"]:
            self.game.anki_answer(update.effective_user.id,
                                  int(query.message.text.split('::')[1]), ease=1)
            query.edit_message_text(text='_{}_'.format(
                query.message.text), parse_mode=telegram.ParseMode.MARKDOWN)
        elif query.data == self.BUTTON["review_2"]:
            self.game.anki_answer(update.effective_user.id,
                                  int(query.message.text.split('::')[1]), ease=2)
            query.edit_message_text(
                text='*{}*'.format(query.message.text), parse_mode=telegram.ParseMode.MARKDOWN)
        elif query.data == self.BUTTON["review_3"]:
            self.game.anki_answer(update.effective_user.id,
                                  int(query.message.text.split('::')[1]), ease=3)
            query.edit_message_text(
                text='*{}*'.format(query.message.text), parse_mode=telegram.ParseMode.MARKDOWN)
        elif query.data == self.BUTTON["review_4"]:
            self.game.anki_answer(update.effective_user.id,
                                  int(query.message.text.split('::')[1]), ease=4)
            query.edit_message_text(
                text='*{}*'.format(query.message.text), parse_mode=telegram.ParseMode.MARKDOWN)
        elif query.data == self.BUTTON["kanji_info"]:
            res = kanji_lookup_str_image(query.message.text)

            for text, fh in res:
                context.bot.send_photo(
                    chat_id=update.effective_chat.id, message='test', photo=fh)

                context.bot.send_message(
                    chat_id=update.effective_chat.id, text=text, parse_mode=telegram.ParseMode.HTML)


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


def sync(update, context):
    try:
        invoke('sync', ANKIPORTS[update.effective_user.id])
        update.message.reply_text('Done')
    except:
        update.message.reply_text('Error')


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
    tellang = TelLang()
    updater.dispatcher.add_handler(CommandHandler('start', tellang.start))
    updater.dispatcher.add_handler(CallbackQueryHandler(tellang.button))
    updater.dispatcher.add_handler(CommandHandler('help', bothelp))
    updater.dispatcher.add_handler(MessageHandler(Filters.text, translate))
    updater.dispatcher.add_handler(CommandHandler('status', status))
    updater.dispatcher.add_handler(CommandHandler('kanji', kanji_lookup))
    updater.dispatcher.add_handler(CommandHandler('t', translate))
    updater.dispatcher.add_handler(CommandHandler('p', tellang.start))
    updater.dispatcher.add_handler(CommandHandler('q', tellang.end_game))
    updater.dispatcher.add_handler(CommandHandler('n', tellang.vote_next))
    updater.dispatcher.add_handler(CommandHandler('sync', sync))
    updater.dispatcher.add_handler(CommandHandler('a', tellang.answer))

    updater.dispatcher.add_error_handler(error)

    updater.dispatcher.add_handler(MessageHandler(Filters.command, unknown))
    # Start the Bot
    updater.start_polling()

    # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()


if __name__ == '__main__':
    main()
