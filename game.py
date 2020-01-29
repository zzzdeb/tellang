#!/usr/bin/env python

import json
import random
import re
import threading
import time
import urllib.request
from datetime import datetime as dt
from enum import Enum

#  from furigana.furigana import split_furigana
import pykakasi
import telegram
from googletrans import Translator

from config import ANKIPORTS, MYTELID


def request(action, **params):
    """
    Request
    """
    return {'action': action, 'params': params, 'version': 6}


def invoke(action, port, **params):
    """
    Docstring
    """
    request_json = json.dumps(request(action, **params)).encode('utf-8')
    response = json.load(urllib.request.urlopen(
        urllib.request.Request('http://localhost:'+port, request_json)))
    if len(response) != 2:
        raise Exception('response has an unexpected number of fields')
    if 'error' not in response:
        raise Exception('response is missing required error field')
    if 'result' not in response:
        raise Exception('response is missing required result field')
    if response['error'] is not None:
        raise Exception(response['error'])
    return response['result']


class State(Enum):
    """
    Docstring
    """
    INIT = 1
    VOTING = 2
    STARTED = 3
    ENDED = 4


class Game:

    def __init__(self):
        """TODO: Docstring for __init__.
        :returns: TODO

        """
        self.state = State.INIT
        self.phase = 0
        self.players = {}
        self.next_voted = set()

        self.context = None
        self.update = None

        self.all_words = {}
        self.answers = {}
        self.words_to_review = {}
        self.current_word = ''
        self.current_value = {}

        self.threshold = 20
        self.current_word_begin_time = dt.now()
        self.last_user_input_time = dt.now()

        k = pykakasi.kakasi()
        k.setMode('K', 'a')
        k.setMode('H', 'a')
        k.setMode('J', 'a')
        k.setMode('s', True)
        self.converter = k.getConverter()
        k = pykakasi.kakasi()
        k.setMode('K', 'a')
        k.setMode('H', 'a')
        k.setMode('J', 'a')
        k.setMode('s', False)
        self.converter1 = k.getConverter()

        self.translator = Translator()

        self.updater = None

    def next_word(self):
        """
        Docstring
        """
        self.next_voted = set()

        if self.current_word in self.answers:
            del self.answers[self.current_word]

        self.phase = 0
        if len(self.answers) == 0:
            self.current_word = ''
        else:
            self.current_word = random.choice(list(self.answers.keys()))
            self.current_value = self.answers[self.current_word]

        # adding to users
        if len(self.current_word) > 0:
            for p in self.players:
                self.players[p]['words_to_review'][self.answers[self.current_word]
                                                   ['id']] = self.current_word

            self.words_to_review[self.answers[self.current_word]
                                 ['id']] = self.current_word

        self.current_word_begin_time = dt.now()
        return self.current_word

    def add_player(self, update, context):
        """
        Docstring
        """
        user = update.effective_user
        if user.id in self.players:
            return 1
        self.players[user.id] = {'fn': user.first_name, 'ln': user.last_name,
                                 'words_to_review': {},
                                 'points': 0}
        try:
            self.players[user.id]['ankiport'] = ANKIPORTS[user.id]
        except KeyError:
            pass
        return 0

    def end_game(self):
        """
        Docstring
        """
        self.state = State.ENDED
        for val in self.players.values():
            if 'ankiport' in val:
                invoke('guiDeckOverview', val['ankiport'],
                       name='Nihongo::Genki 1 & 2, Incl Genki 1 Supplementary Vocab')
                invoke('sync', val['ankiport'])
                invoke('guiDeckOverview', val['ankiport'],
                       name='Nihongo::Genki 1 & 2, Incl Genki 1 Supplementary Vocab')
        return 0

    def winner_str(self):
        """
        Docstring
        """
        winner = self.players[max(
            self.players, key=lambda x: self.players[x]['points'])]
        text = 'Winner: {}, {}  🎆🎆🎆'.format(winner['fn'], winner['ln'])
        return text

    def check_if_game_done(self):
        """
        Docstring
        """
        return self.current_word == '' or (max(list([a['points'] for a in self.players.values()])) if len(self.players) else 0) >= self.threshold

    def status(self):
        """
        Docstring
        """
        text = ''
        for v in self.players.values():
            text += '{}, {}: {}, '.format(v['fn'], v['ln'], v['points'])
        return text[:-2]

    def timer(self):
        """
        Docstring
        """
        while self.state == State.STARTED:
            delta = dt.now() - self.current_word_begin_time
            if delta.seconds > 0 and self.phase == 0:
                hiragana = re.sub(r'\[[^]]*\]', '', self.current_word)

                #  str(self.players)+'\n *'+hiragana+'*'
                self.context.bot.send_message(chat_id=self.update.effective_chat.id,
                                              text='{}\n*{}*'.format(
                                                  self.status(), hiragana),
                                              parse_mode=telegram.ParseMode.MARKDOWN)
                self.phase = 1 if (self.answers[self.current_word]['type'] ==
                                   'Recognition' and not self.current_word == self.answers[self.current_word]['Reading']) else 2
            if delta.seconds > 8 and self.phase == 1:
                self.context.bot.send_message(chat_id=self.update.effective_chat.id,
                                              text=self.answers[self.current_word]['Reading'])
                self.phase = 2
            if delta.seconds > 20:
                text = self.answer_str()
                self.context.bot.send_message(chat_id=self.update.effective_chat.id,
                                              text=text)

                self.next_word()

                if self.check_if_game_done():
                    self.end_game()

            time.sleep(0.1)

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
            answers = [re.sub(r'\([^)]*\)', '', a).strip().lower()
                       for a in ansval['Meaning'].replace(',', ';').replace('...', '').split(';')]
        elif ansval['type'] == 'Recall':
            answers = [re.sub(r'\([^)]*\)', '', a).strip().lower()
                       for a in ansval['Expression'].replace(',', ';').replace('...', '').split(';')]
            answers = [re.sub(r'\（[^)]*\）', '', a).strip().lower()
                       for a in ansval['Expression'].replace(',', ';').replace('...', '').split(';')]
            answers += [self.converter1.do(v) for v in answers]
            print(answers)
        return ans in answers

    def answer_str(self, word=''):
        """TODO: Docstring for print_answer.
        :returns: TODO

        """
        w = word if word != '' else self.current_word

        text = ''
        if self.all_words[w]['type'] == 'Recognition':
            text = w + ' : '+self.all_words[w]['Meaning']
        elif self.all_words[w]['type'] == 'Recall':
            text = '%s : %s (%s)' % (w, self.all_words[w]['Expression'], self.converter1.do(
                self.all_words[w]['Expression']))
        return text

    def start(self):
        """
        Docstring
        """
        if self.state == State.INIT:
            self.state = State.STARTED

            result = None
            for val in self.players.values():
                try:
                    # Preparing anki
                    invoke(
                        'guiDeckOverview', val['ankiport'], name='Nihongo::Genki 1 & 2, Incl Genki 1 Supplementary Vocab')
                    invoke('sync', val['ankiport'])
                    invoke(
                        'guiDeckOverview', val['ankiport'], name='Nihongo::Genki 1 & 2, Incl Genki 1 Supplementary Vocab')

                    #  print(val['fn'])
                    val['ankiCards'] = invoke(
                        'findCards', val['ankiport'], query='"deck:Nihongo::Genki 1 & 2, Incl Genki 1 Supplementary Vocab" prop:due<1')
                    #  print(val['ankiCards'])
                    if result == None:
                        result = set(val['ankiCards'])
                    else:
                        result = result & set(val['ankiCards'])
                except KeyError:
                    print('KeyError')

            result = list(result)

            # print(result)
            for a in invoke('cardsInfo', self.players[MYTELID]['ankiport'], cards=result):
                value = {}
                value['id'] = int(a['cardId'])
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

            #  self.answers = {'August': {'type': 'Recall', 'Reading': 'Aug', 'Expression': 'aug'}, 'Sep': {
                #  'type': 'Recall', 'Reading': 'Aug', 'Expression': 'aug'}}
            #  self.answers = {'August': {'type': 'Recall', 'Reading': 'Aug',
                    #  'Expression': 'aug'}, 'Sep': 'Sep , Okt; Mit ...'}
            #  self.answers= {'（〜を）おねがいします' :'..., please.'}
            self.all_words = self.answers.copy()
            self.next_word()
            thread = threading.Thread(target=self.timer)
            thread.start()

        elif self.state == State.STARTED:
            self.context.bot.send_message(chat_id=self.update.effective_chat.id,
                                          text="Game running")
        return 0

    def vote_next(self, player_id):
        """
        Docstring
        """
        self.next_voted.add(player_id)
        if len(self.next_voted) == len(self.players):
            text = self.answer_str()
            self.context.bot.send_message(chat_id=self.update.effective_chat.id,
                                          text=text)
            self.next_word()
            if self.check_if_game_done():
                self.end_game()
            return True

        return False

    def anki_answer(self, pid, cid, ease=2):
        """
        Docstring
        """
        if 'ankiport' in self.players[pid]:
            if invoke('areDue', self.players[pid]['ankiport'], cards=[cid])[0]:
                print('Answering {}:{}'.format(
                    self.players[pid]['words_to_review'][cid], cid))
                invoke('answerCard', self.players[pid]
                       ['ankiport'], cid=cid, ease=ease)
                del self.players[pid]['words_to_review'][cid]
            else:
                print('Not Due so not answering {}:{}'.format(
                    self.players[pid]['words_to_review'][cid], cid))
        else:
            print('Player not anki {}:{}'.format(
                self.players[pid]['words_to_review'][cid], cid))

    def answer(self, player_id, answer):
        """
        Docstring
        """
        if self.is_right_answer(answer):
            self.players[player_id]['points'] += 1
            if 'ankiport' in self.players[player_id]:
                self.anki_answer(player_id, self.current_value['id'])
            else:
                del self.players[player_id]['words_to_review'][self.current_value['id']]

            self.next_word()
            if self.check_if_game_done():
                self.end_game()
            return 1

        return 0
