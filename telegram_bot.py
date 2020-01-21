import json
import random
import time
from datetime import datetime as dt
import urllib.request
import threading
import re

import requests
from furigana.furigana import split_furigana
import pykakasi
from googletrans import Translator
import telegram

from config import TELEGRAM_SEND_MESSAGE_URL
from config import MYTELID


def request(action, **params):
    return {'action': action, 'params': params, 'version': 6}


def invoke(action, **params):
    requestJson = json.dumps(request(action, **params)).encode('utf-8')
    response = json.load(urllib.request.urlopen(
        urllib.request.Request('http://localhost:8766', requestJson)))
    if len(response) != 2:
        raise Exception('response has an unexpected number of fields')
    if 'error' not in response:
        raise Exception('response is missing required error field')
    if 'result' not in response:
        raise Exception('response is missing required result field')
    if response['error'] is not None:
        raise Exception(response['error'])
    return response['result']

class Game:

    def __init__(self, telbot):
        """TODO: Docstring for __init__.
        :returns: TODO

        """
        self.players = {'a':0}
        self.answers = {}
        self.telbot = telbot
        self.current_word = ''
        self.current_value = {}
        self.phase = 0
        self.threshold = 10
        self.current_word_begin_time = dt.now()
        self.last_user_input_time = dt.now()
        self.isOn = False
        k = pykakasi.kakasi()
        k.setMode('K','a')
        k.setMode('H','a')
        k.setMode('J','a')
        k.setMode('s', True)
        self.converter = k.getConverter()
        k = pykakasi.kakasi()
        k.setMode('K','a')
        k.setMode('H','a')
        k.setMode('J','a')
        k.setMode('s', False)
        self.converter1 = k.getConverter()

    def next_word(self):
        if len(self.current_word) > 0:
            del self.answers[self.current_word]

        self.phase = 0
        if len(self.answers) == 0:
            self.current_word = ''
        else:
            self.current_word = random.choice(list(self.answers.keys()))
            self.current_value = self.answers[self.current_word]
        self.current_word_begin_time = dt.now()
        return self.current_word

    def end_game(self, announce_winner=True):
        self.isOn = False
        self.telbot.game_started = False
        self.telbot.current_game_index = -1

        self.telbot.outgoing_message_text = ''
        if announce_winner:
            self.telbot.outgoing_message_text = 'Winner: '+max(self.players, key=self.players.get) + '🎆\n'
        self.telbot.outgoing_message_text += 'END'
        self.telbot.send_message()
        return 0

    def check_if_game_done(self):
        return self.current_word == '' or (max(list(self.players.values())) if len(self.players) else 0) >= self.threshold

    def timer(self):
        while(self.isOn):
            delta = dt.now()- self.current_word_begin_time
            if delta.seconds > 0 and self.phase ==0:
                hiragana = re.sub(r'\[[^]]*\]', '', self.current_word)
                self.telbot.outgoing_message_text = str(self.players)+'\n Next word: '+hiragana
                self.telbot.send_message()
                self.phase = 1 if (self.answers[self.current_word]['type'] == 'Recognition' and not self.current_word == self.answers[self.current_word]['Reading']) else 2
            if delta.seconds > 8 and self.phase ==1:
                self.telbot.outgoing_message_text = self.answers[self.current_word]['Reading']
                self.telbot.send_message()
                self.phase = 2
            if delta.seconds > 20:
                text = self.answer_str()
                self.telbot.outgoing_message_text = text
                self.telbot.send_message()

                self.next_word()

                if self.check_if_game_done():
                    self.telbot.outgoing_message_text = self.end_game()
                    self.telbot.send_message()

            time.sleep(0.1)
        return

    def is_right_answer(self, answer):
        """TODO: Docstring for is_right_answer.

        :answer: TODO
        :returns: TODO

        """
        if not answer.startswith('/a '):
            return 0
        ans = answer[3:].lower()
        ansval = self.answers[self.current_word]
        answers = []
        if ansval['type'] == 'Recognition':
            answers = [re.sub(r'\([^)]*\)', '', a).strip().lower() for a in ansval['Meaning'].replace(',',';').replace('...', '').split(';')]
        elif ansval['type'] == 'Recall':
            answers.append(self.converter1.do(ansval['Expression']))
        return ans in answers


    def answer_str(self):
        """TODO: Docstring for print_answer.
        :returns: TODO

        """

        text = ''
        if self.answers[self.current_word]['type'] == 'Recognition':
            text = self.current_word +' : '+self.answers[self.current_word]['Meaning']
        elif self.answers[self.current_word]['type'] == 'Recall':
            text = '%s : %s (%s)' % (self.current_word, self.answers[self.current_word]['Expression'], self.converter1.do(self.answers[self.current_word]['Expression']))
        return text


    def run(self, telbot):

        if telbot.incoming_message_text.startswith('/p'):
            self.isOn = True
            self.players = {'a':0}
            result = invoke('findCards', query='"deck:Nihongo::Genki 1 & 2, Incl Genki 1 Supplementary Vocab" prop:due<1')
            # print(result)
            for a in invoke('cardsInfo', cards=result):
                value = {}
                value['id'] = a['cardId']
                if a['template']['name'] == 'Recall':
                    value['type'] = 'Recall'
                    value['Reading'] = a['fields']['Reading']['value']
                    value['Expression'] = a['fields']['Expression']['value']
                    self.answers[a['fields']['Meaning']['value']] = value
                elif a['template']['name'] == 'Recognition':
                    value['type'] = 'Recognition'
                    value['Meaning'] = a['fields']['Meaning']['value']
                    value['Reading'] = a['fields']['Reading']['value']
                    self.answers[a['fields']['Expression']['value']] = value

            #  self.answers = {'August':'August', 'Sep':'Sep , Okt; Mit ...'}
            #  self.answers= {'（〜を）おねがいします' :'..., please.'}
            #  self.telbot.outgoing_message_text = str(self.answers)
            #  self.telbot.send_message()
            self.next_word()

            thread = threading.Thread(target=self.timer)
            thread.start()
            return 0

        if self.telbot.incoming_message_text.startswith('/a'):
            if self.is_right_answer(self.telbot.incoming_message_text):
                playerstr = telbot.first_name + ', ' + telbot.last_name
                try:
                    self.players[playerstr] += 1
                except KeyError:
                    self.players[playerstr] = 1

                if self.telbot.from_id == MYTELID:
                    invoke('answerCard', cid=self.current_value['id'])
                else:
                    print('not zzz')

                self.next_word()
                if self.check_if_game_done():
                    return self.end_game()

                #  self.telbot.outgoing_message_text = str(self.players)
                #  self.telbot.send_message()
            return 0

        if telbot.incoming_message_text == '/n':
            text = self.answer_str()

            self.next_word()
            if self.check_if_game_done():
                return self.end_game()

            self.telbot.outgoing_message_text = text #+ '\n' + str(self.players)+'\n Next word: '+self.current_word
            self.telbot.send_message()
            return 0

        if telbot.incoming_message_text == '/q':
            self.telbot.outgoing_message_text = self.answer_str()
            return self.end_game(announce_winner=False)





class TelegramBot:

    def __init__(self):
        """"
        Initializes an instance of the TelegramBot class.

        Attributes:
            chat_id:str: Chat ID of Telegram chat, used to identify which conversation outgoing messages should be send to.
            text:str: Text of Telegram chat
            first_name:str: First name of the user who sent the message
            last_name:str: Last name of the user who sent the message
        """

        self.chat_id = None
        self.text = None
        self.first_name = None
        self.last_name = None
        self.translator = Translator()
        self.current_game_index = -1
        self.games = [Game(self)]
        self.game_started = False


    def parse_webhook_data(self, data):
        """
        Parses Telegram JSON request from webhook and sets fields for conditional actions

        Args:
            data:str: JSON string of data
        """

        try:
            message = data['message']
        except KeyError:
            try:
                message = data['edited_message']
            except KeyError:
                print(data)
                raise KeyError

        self.chat_id = message['chat']['id']
        try:
            self.incoming_message_text = message['text'].lower()
        except KeyError:
            self.incoming_message_text = ''
        self.from_id = message['from']['id']
        self.first_name = message['from']['first_name']
        self.last_name = message['from']['last_name']


    def action(self):
        """
        Conditional actions based on set webhook data.

        Returns:
            bool: True if the action was completed successfully else false
        """

        success = None

        if self.incoming_message_text == '/hello':
            self.outgoing_message_text = "Hello {} {}! Dont be mad".format(self.first_name, self.last_name)
            success = self.send_message()

        if self.incoming_message_text == '/rad':
            self.outgoing_message_text = '🤙'
            success = self.send_message()

        if self.incoming_message_text.startswith('/t ') or self.incoming_message_text.startswith('tt '):
            text = self.translator.translate(self.incoming_message_text[3:], dest='ja').text
            text = text+'\n'
            twoLines = False
            for pair in split_furigana(text):
                if len(pair)==2:
                    twoLines = True

            if twoLines:
                for pair in split_furigana(text):
                    if len(pair)==2:
                        kanji,hira = pair
                        text = text + "%s(%s)" % (kanji,hira)
                    else:
                        text = text+pair[0]
            self.outgoing_message_text = text
            success = self.send_message()

        if self.incoming_message_text.startswith('/p'):
            if not self.game_started:
                self.game_started = True
                self.current_game_index = 0
                self.games[self.current_game_index].run(self)
            else:
                self.outgoing_message_text = 'Game running'
                success = self.send_message()

        if self.game_started:
            if self.incoming_message_text.startswith('/a') or self.incoming_message_text.startswith('/n') or self.incoming_message_text.startswith('/q'):
                self.games[self.current_game_index].run(self)

        return success


    def send_message(self):
        """
        Sends message to Telegram servers.
        """

        custom_keyboard = [['top-left', 'top-right'], 
                           ['bottom-left', 'bottom-right']]
        reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard)
        res = requests.get(TELEGRAM_SEND_MESSAGE_URL.format(self.chat_id, self.outgoing_message_text, reply_markup))

        return True if res.status_code == 200 else False


    @staticmethod
    def init_webhook(url):
        """
        Initializes the webhook

        Args:
            url:str: Provides the telegram server with a endpoint for webhook data
        """

        requests.get(url)
