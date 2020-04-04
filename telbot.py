#!/usr/bin/env python

import argparse
import ast
import base64
import logging
import subprocess
import xml.etree.ElementTree as ET
from io import BytesIO
from io import StringIO  # Python3 use: from io import StringIO
import sys

from helper import tel_argparse
import telegram
from furigana.furigana import split_furigana
from googletrans import Translator
from gtts import gTTS
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (CallbackQueryHandler, CommandHandler, Filters,
                          MessageHandler, Updater)

from config import ANKIPORTS, TOKEN
from game import Game, State, invoke
from game_4000 import English4000Game
from game_ja_2000 import Game_ja2000
from game_kanji import KanjiGame
from game_500 import Game_500

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

updater = Updater(TOKEN, use_context=True)

ANKIDECKS = {
    'genki':  [Game, "Nihongo::Genki 1 & 2, Incl Genki 1 Supplementary Vocab"],
    'kanji':  [KanjiGame, "Nihongo::01 NihongoShark.com: Kanji - with mn"],
    'op': [Game, "Nihongo::One Piece Vocabulary"],
    'onepiece': [Game, "Nihongo::One Piece Vocabulary"],
    'j1': [Game_ja2000, "Nihongo::Japanese Core 2000 Step 01 Listening Sentence Vocab + Images"],
    'j2': [Game_ja2000, "Nihongo::Japanese Core 2000 Step 02 Listening Sentence Vocab + Images"],
    'eng': [English4000Game, "English::4000 Essential English Words"],
    '500': [Game_500, "English::English First 500 - Green Yurt (mn)"],
}


def kanji_lookup_str_image(text):
    port = '8766'
    res = []
    for kanji in text:
        nids = invoke('findNotes', port,
                      query='"deck:Nihongo::01 NihongoShark.com: Kanji - with mn" kanji:{}'.format(kanji))
        if len(nids) != 1:
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


def word_lookup_audio(delay=5, cardsnum=1):
    """TODO: Docstring for word_lookup_audio.

    :arg1: TODO
    :returns: TODO

    """
    val = {'ankiport': '8766'}
    res = []
    #  text = ''
    deckname = "Nihongo::Genki 1 & 2, Incl Genki 1 Supplementary Vocab"
    dummy_audio = '/tmp/dummy.mp3'
    lang = 'en'
    src_audio = '/tmp/tellangsrc.mp3'
    dst_audio = '/tmp/tellangdst.mp3'
    out_audio = '/tmp/tellangout.mp3'
    name = 'name'

    #  look = ['kanji', 'keyword', 'constituent', 'myStory',
    #  'heisigStory', 'koohiiStory1', 'onYomi', 'kunYomi']
    #  media = ['strokeDiagram']

    # Sync anki
    #  invoke(
    #  'guiDeckOverview', val['ankiport'], name=deckname)
    #  invoke('sync', val['ankiport'])
    #  invoke(
    #  'guiDeckOverview', val['ankiport'], name=deckname)

    #  print(val['fn'])
    query = '"deck:{}" (is:learn or prop:due<1)'.format(deckname)
    val['ankiCards'] = invoke(
        'findCards', val['ankiport'], query=query)
    #  print(val['ankiCards'])

    cids = val['ankiCards'][:cardsnum] if len(
        val['ankiCards']) > cardsnum-1 else val['ankiCards']
    #  print(cids)

    subprocess.call('ffmpeg -y -f lavfi -i anullsrc -t {} '.format(delay) +
                    dummy_audio, shell=True)  # returns the exit code in unix
    for a in invoke('cardsInfo', val['ankiport'], cards=cids):
        value = {}
        value['id'] = int(a['cardId'])
        value['answerButtons'] = a['answerButtons']
        value['Expression'] = a['fields']['Expression']['value']
        value['Meaning'] = a['fields']['Meaning']['value']
        value['Reading'] = a['fields']['Reading']['value']
        eng_audio = ''
        ja_audio = ''

        if a['template']['name'] == 'Recall':
            value['type'] = 'Recall'
            value['src'] = value['Meaning']
            value['dst'] = value['Expression']
            eng_audio = src_audio
            ja_audio = dst_audio
            name = value['Meaning']

        elif a['template']['name'] == 'Recognition':
            value['type'] = 'Recognition'
            value['src'] = value['Expression']
            value['dst'] = value['Meaning']
            ja_audio = src_audio
            eng_audio = dst_audio
            name = value['Expression']

        encoded_audio = invoke('retrieveMediaFile',
                               val['ankiport'], filename=a['fields']['Audio']['value'][7:-1])
        # jap_audio
        with open(ja_audio, 'wb') as f:
            f.write(base64.b64decode(encoded_audio))

        # eng_audio
        tts = gTTS(a['fields']['Meaning']['value'], lang=lang)
        tts.save(eng_audio)

        # concat
        returned_value = subprocess.call('ffmpeg -y -i "concat:{}|{}|{}" {}'.format(
            src_audio, dummy_audio, dst_audio, out_audio), shell=True)  # returns the exit code in unix

        with open(out_audio, 'rb') as f:
            value['audioQuiz'] = BytesIO(f.read())
        print('Name '+name)
        value['audioQuiz'].name = name

        res.append(value)
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
    if not context.args is None:
        msg = ' '.join(context.args)
    else:
        msg = update.message.text
    text = translator.translate(msg, dest='ja').text
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

    def __init__(self, id):
        """TODO: to be defined. """
        self.game = Game()
        self.updater = Updater(TOKEN, use_context=True)
        self.review_mode = 'audio'
        self.id = id
        self.status = State.INIT
        self.update = None
        self.checker_job = None

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
        self.HARD = ['😠', '😈', '🙂', '😇']

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

    def send_words_to_review(self, context, with_answer_buttons=True):
        nameLen = 65
        for p, val in self.game.players.items():
            for i, cid in enumerate(self.game.all_words[self.game.all_words[p]].index):
                markup = ''
                buttonsText = self.game.all_words['nextReviews'].loc[cid]
                buttons = len(buttonsText)
                review_button = [[InlineKeyboardButton(
                    self.HARD[i]+ ':' + text, callback_data=self.BUTTON["review_"+str(i+1)]) for i, text in enumerate(buttonsText)]]
                new_list = [review_button[0]
                            [:buttons], [self.kanji_info_button]]

                callback_data = {
                    'cid': cid,
                    'tellangid': self.id
                }

                new_list[1].append(InlineKeyboardButton(".",
                                                        callback_data=str(callback_data)))

                if with_answer_buttons:
                    markup = InlineKeyboardMarkup(new_list)

                if self.review_mode == 'audio':
                    audio = self.game.answer_audio(cid)
                    text = self.game.answer_str(cid)
                    context.bot.send_audio(
                        chat_id=p, audio=audio, title=text, caption='{}. {}'.format(i+1, text), reply_markup=markup)
                elif self.review_mode == 'audio_quiz':
                    audio = self.game.answer_audio(cid, asquiz=True)
                    text = self.game.answer_str(cid)
                    context.bot.send_audio(
                        chat_id=p, audio=audio, title=text, caption='{}. {}'.format(i+1, text), reply_markup=markup)
                else:
                    text = self.game.answer_str(cid)
                    text = '{}. {}'.format(i+1, text)
                    context.bot.send_message(
                        chat_id=p, text=text, reply_markup=markup)

    def check(self, context):
        """
        Docstr
        """
        if self.game.state == State.ENDED:
            self.game.state = State.INIT
            self.end_game(self.update, context, announce_winner=True)

    def start(self, update, context):
        """
        Docstr
        """
        parser = argparse.ArgumentParser(description='anki start parser.')
        parser.add_argument('-d', metavar='DECKNAME', type=str, nargs='?',
                            choices=ANKIDECKS.keys(), help='AnkiDeckname', default="genki")
        parser.add_argument('-n', metavar='WINTHRESHOLD',
                            type=int, nargs='?', help='Points to win', default=20)

        args = tel_argparse(parser, update, context)
        if args is None:
            return 0

        if self.game.state in [State.INIT, State.ENDED]:
            self.game = Game()
            self.update = update
            key = args.d
            if key in ANKIDECKS:
                self.game = ANKIDECKS[key][0]()
                self.game.deckname = ANKIDECKS[key][1]
            self.review_mode = 'audio' if self.game.withaudio else 'text'
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
            self.checker_job = updater.job_queue.run_repeating(self.check, 0.1,
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

    def end_game(self, update, context, announce_winner=False):
        """
        Docstr
        """
        text = ''
        if announce_winner:
            text += self.game.winner_str() + '🎆🎆🎆\n'
        text += 'END'
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=text)
        self.checker_job.schedule_removal()
        self.game.end_game()

        self.send_words_to_review(context)
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
        """TODO: Docstring for button.

        :update: TODO
        :context: TODO
        :returns: TODO

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

class TelLangAudio(TelLang):

    """Docstring for TelLangAudio. """

    def __init__(self, id):
        """TODO: to be defined. """
        TelLang.__init__(self, id)
        self.num = 10
        self.deckname = None
        self.game = Game()

    def send_audios(self, update, context):
        self.game.add_player(update.effective_user)
        self.game.start()
        self.game.state = State.ENDED

        starttext = 'From {} words'
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=starttext.format(len(self.game.all_words)))

        for i in range(0, self.num-1):
            self.game.next_word()

        self.review_mode = 'audio_quiz'
        self.send_words_to_review(context)

class AllGame:

    """Docstring for AllGame. """

    def __init__(self):
        """TODO: to be defined. """
        self.games = {}
        self.end_games = {}
        self.BUTTON = {
            'review_1': '3',
            'review_2': '4',
            'review_3': '5',
            'review_4': '6',
            'kanji_info': '8',
        }

    def command(self, update, context):
        """TODO: Docstring for command.

        :update: TODO
        :context: TODO
        :returns: TODO

        """
        parser = argparse.ArgumentParser(description='anki audio parser.')
        parser = argparse.ArgumentParser(description='anki audio parser.')
        parser = argparse.ArgumentParser(description='anki audio parser.')
        parser.add_argument('-n', metavar='NUMBER', type=int, nargs='?',
                            help='Number of cards to review', default=10)
        parser.add_argument('-d', metavar='DECKNAME', type=str, nargs='?',
                            help='AnkiDeckname', default="genki")

    def addgame(self, id, tellang=TelLang):
        """TODO: Docstring for addgame.

        :id: TODO
        :returns: TODO

        """
        self.games[id] = tellang(id)
        return self.games[id]

    def start(self, update, context):

        chid = update.effective_chat.id
        if chid in self.games:
            self.games[chid].start(update, context)
        else:
            self.addgame(chid)
            self.games[chid].start(update, context)

    def end_game(self, update, context):
        chid = update.effective_chat.id
        if chid in self.games:
            self.games[chid].end_game(update, context)

    def vote_next(self, update, context):
        chid = update.effective_chat.id
        if chid in self.games:
            self.games[chid].vote_next(update, context)

    def button(self, update, context):
        """
        Docstr
        """
        chid = update.effective_chat.id
        query = update.callback_query
        if query.data in [self.BUTTON["review_1"], self.BUTTON["review_2"], self.BUTTON["review_3"], self.BUTTON["review_4"]]:
            callback_data = ast.literal_eval(
                query.message.reply_markup.inline_keyboard[1][-1]['callback_data'])
            cid = callback_data['cid']
            tellangid = callback_data['tellangid']
            tellang = self.games[tellangid]

            invoke('guiDeckOverview',
                   tellang.game.players[chid]['ankiport'], name=tellang.game.deckname)

            if query.data == self.BUTTON["review_1"]:
                tellang.game.anki_answer(update.effective_user.id, cid, ease=1)
                #  query.edit_message_text(text='_{}_'.format(
                #  query.message.text), parse_mode=telegram.ParseMode.MARKDOWN)
            elif query.data == self.BUTTON["review_2"]:
                tellang.game.anki_answer(update.effective_user.id, cid, ease=2)
            elif query.data == self.BUTTON["review_3"]:
                tellang.game.anki_answer(update.effective_user.id, cid, ease=3)
            elif query.data == self.BUTTON["review_4"]:
                tellang.game.anki_answer(update.effective_user.id, cid, ease=4)
            query.edit_message_reply_markup(reply_markup='')
        elif query.data == self.BUTTON["kanji_info"]:
            res = kanji_lookup_str_image(query.message.text)

            for text, fh in res:
                context.bot.send_photo(
                    chat_id=update.effective_chat.id, message='test', photo=fh)

                context.bot.send_message(
                    chat_id=update.effective_chat.id, text=text, parse_mode=telegram.ParseMode.HTML)
        elif query.data.startswith('ankiaudio_'):
            rest = query.data[10:]
            if rest.startswith('deck_'):
                key = rest[5:]
                self.games[update.effective_chat.id].game.deckname = ANKIDECKS[key][1]

                buttons = [[InlineKeyboardButton(ind, callback_data='ankiaudio_num_'+str(ind)) for ind in [10, 20, 50, 100]]]
                button_markup = InlineKeyboardMarkup(buttons)
                query.edit_message_text(text='Deck: {}\nNumber:'.format(key), reply_markup=button_markup)
                return
            elif rest.startswith('num_'):
                num = int(rest[4:])
                self.games[update.effective_chat.id].num = num

                buttons = [[InlineKeyboardButton(str(ind), callback_data='ankiaudio_N_'+str(ind)) for ind in [False, True]]]
                button_markup = InlineKeyboardMarkup(buttons)
                query.edit_message_text(text='{} {}\nNew words?:'.format(query.message.text, num), reply_markup=button_markup)
                return
            elif rest.startswith('N_'):
                new = bool(rest[2:])
                tellang = self.games[update.effective_chat.id]
                if new:
                    tellang.game.deckfilter = 'is:new -is:buried -is:suspended'
                tellang.send_audios(update, context)

        else:
            if chid in self.games:
                self.games[chid].button(update, context)


    def answer(self, update, context):
        chid = update.effective_chat.id
        if chid in self.games:
            self.games[chid].answer(update, context)

    def listgames(self, update, context):
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=str(self.games))


    def anki_audio(self, update, context):
        """TODO: Docstring for ankie_audio.
        1. Find 30 words
        2. TTS on words
        3. connect audios
        4. send audio

        :arg1: TODO
        :returns: TODO
        """
        tellang = self.addgame(update.effective_chat.id, tellang=TelLangAudio)
        tellang.game.random = False
        print('Args: '+str(context.args))

        if context.args == []:
            buttons = [[InlineKeyboardButton(ind, callback_data='ankiaudio_deck_'+ind)] for ind in ANKIDECKS]
            button_markup = InlineKeyboardMarkup(buttons)
            context.bot.send_message(chat_id=update.effective_chat.id, text='From deck:', reply_markup=button_markup)
            return

        parser = argparse.ArgumentParser(description='anki audio parser.')
        parser.add_argument('-n', metavar='NUMBER', type=int, nargs='?',
                            help='Number of cards to review', default=10)
        parser.add_argument('-d', metavar='DECKNAME', type=str, nargs='?',
                            choices=ANKIDECKS.keys(), help='AnkiDeckname', default="genki")
        parser.add_argument('-N', action='store_true', help='From New Cards')

        args = tel_argparse(parser, update, context)
        if args is None:
            return 0

        tellang.num = args.n
        key = ''
        if args.d in ANKIDECKS:
            key = args.d
            tellang.game = ANKIDECKS[key][0]()
            tellang.game.deckname = ANKIDECKS[key][1]

        if args.N:
            tellang.game.deckfilter = 'is:new -is:buried -is:suspended'

        tellang.send_audios(update, context)

def bothelp(update, context):
    """
    Docstr
    """
    update.message.reply_text("Use /start to test this bot.")


def error(update, context):
    """Log Errors caused by Updates."""
    LOGGER.warning('Update "%s" caused error "%s"', update, context.error)


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
    allgame = AllGame()
    updater.dispatcher.add_handler(CommandHandler('start', allgame.start))
    updater.dispatcher.add_handler(CallbackQueryHandler(allgame.button))
    updater.dispatcher.add_handler(CommandHandler('help', bothelp))
    updater.dispatcher.add_handler(CommandHandler('status', status))
    updater.dispatcher.add_handler(CommandHandler('kanji', kanji_lookup))
    updater.dispatcher.add_handler(CommandHandler('t', translate))
    updater.dispatcher.add_handler(CommandHandler('p', allgame.start))
    updater.dispatcher.add_handler(CommandHandler('q', allgame.end_game))
    updater.dispatcher.add_handler(CommandHandler('n', allgame.vote_next))
    updater.dispatcher.add_handler(CommandHandler('sync', sync))
    updater.dispatcher.add_handler(
        CommandHandler('ankiaudio', allgame.anki_audio))
    updater.dispatcher.add_handler(
        CommandHandler('aa', allgame.anki_audio))
    updater.dispatcher.add_handler(CommandHandler('a', allgame.command))
    updater.dispatcher.add_handler(CommandHandler('list', allgame.listgames))

    #  updater.dispatcher.add_error_handler(error)

    updater.dispatcher.add_handler(MessageHandler(Filters.command, unknown))

    updater.dispatcher.add_handler(MessageHandler(Filters.text, translate))
    # Start the Bot
    updater.start_polling()

    # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()


if __name__ == '__main__':
    main()
