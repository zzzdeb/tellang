#!/usr/bin/env python

import subprocess
import base64
from io import BytesIO
import random
import re
import threading
import time
from datetime import datetime as dt
from enum import Enum
from helper import invoke, get_silence

#  from furigana.furigana import split_furigana
import pykakasi
import telegram
from googletrans import Translator
from gtts import gTTS
import pandas as pd

from config import ANKIPORTS

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

        self.all_words = pd.DataFrame()
        self.current_word = None
        self.random = False
        self.withaudio = True

        self.threshold = 20
        self.current_word_begin_time = dt.now()
        self.last_user_input_time = dt.now()

        self.deckname = "Nihongo::Genki 1 & 2, Incl Genki 1 Supplementary Vocab"

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
        df = self.all_words

        self.phase = 0

        notanswered = df[df['NotSeen']]
        if len(notanswered) > 0:
            #  print(notanswered)
            if self.random:
                self.current_word = notanswered.sample(1).iloc[0]
            else:
                self.current_word = notanswered.iloc[0]
            df.at[self.current_word.name, 'NotSeen'] = False
            # mark to as review !!!
            df.update(pd.DataFrame(True, columns=list(
                self.players.keys()), index=[self.current_word.name]))
        else:
            self.current_word = None

        self.current_word_begin_time = dt.now()
        return self.current_word

    def add_player_pure(self, tid, fn, ln, with_anki=True):
        """
        Docstring
        """
        if tid in self.players:
            if with_anki and (tid in ANKIPORTS):
                self.players[tid]['ankiport'] = ANKIPORTS[tid]
            else:
                if 'ankiport' in self.players[tid]:
                    del self.players[tid]['ankiport']
            return 1
        self.players[tid] = {'fn': fn, 'ln': ln,
                                 'points': 0}
        #  print(self.all_words.columns)
        self.all_words[tid] = pd.Series(False, index=self.all_words.index)
        #  print(self.all_words.columns)

        try:
            if with_anki:
                self.players[tid]['ankiport'] = ANKIPORTS[tid]
        except KeyError:
            pass
        return 0
    
    def add_player(self, user, with_anki=True):
        """
        Docstring
        """
        return self.add_player_pure(user.id, user.first_name, user.last_name)

    def end_game(self):
        """
        Docstring
        """
        self.state = State.ENDED
        for val in self.players.values():
            if 'ankiport' in val:
                invoke('guiDeckOverview', val['ankiport'],
                       name=self.deckname)
                invoke('sync', val['ankiport'])
                invoke('guiDeckOverview', val['ankiport'],
                       name=self.deckname)
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
        return type(self.current_word) != pd.Series or (max(list([a['points'] for a in self.players.values()])) if len(self.players) else 0) >= self.threshold

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
            word = self.current_word
            kanji = re.sub(r'\[[^]]*\]', '', self.current_word['Expression'])
            ask = kanji if word['Type'] == 'Recognition' else word['Meaning']
            if delta.seconds > 0 and self.phase == 0:
                self.context.bot.send_message(chat_id=self.update.effective_chat.id,
                                              text='{}\n*{}*'.format(
                                                  self.status(), ask),
                                              parse_mode=telegram.ParseMode.MARKDOWN)
                # 2 round if it contains kanji
                self.phase = 1 if (self.current_word['Type'] ==
                                   'Recognition' and not self.current_word['Expression'] == self.current_word['Reading']) else 2
            if delta.seconds > 8 and self.phase == 1:
                self.context.bot.send_message(chat_id=self.update.effective_chat.id,
                                              text=self.current_word['Reading'])
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
        ans = answer.lower()
        answers = []
        if self.current_word['Type'] == 'Recognition':
            answers = [re.sub(r'\([^)]*\)', '', a).strip().lower()
                       for a in self.current_word['Meaning'].replace(',', ';').replace('...', '').split(';')]
        elif self.current_word['Type'] == 'Recall':
            answers = [re.sub(r'\([^)]*\)', '', a).strip().lower()
                       for a in self.current_word['Expression'].replace(',', ';').replace('...', '').split(';')]
            answers = [re.sub(r'\（[^)]*\）', '', a).strip().lower()
                       for a in self.current_word['Expression'].replace(',', ';').replace('...', '').split(';')]
            answers += [self.converter1.do(v) for v in answers]
        print(answers)
        return ans in answers

    def answer_str(self, cid=None):
        """TODO: Docstring for print_answer.
        :returns: TODO

        """
        if cid == None:
            cid = self.current_word.name
        df = self.all_words
        cardinfo = df.loc[cid]

        text = ''
        if cardinfo['Type'] == 'Recognition':
            text = '%s : %s' % (cardinfo['Expression'], cardinfo['Meaning'])
        elif cardinfo['Type'] == 'Recall':
            text = '%s : %s' % (cardinfo['Meaning'], cardinfo['Expression'])
        return text

    def prepare_answers(self, cids):
        """
        Doc
        """
        for pinfo in self.players.values():
            if 'ankiport' in pinfo:
                infos = invoke('cardsInfo', pinfo['ankiport'], cards=cids)
                fields = list(infos[0]['fields'].keys())
                others = list(infos[0].keys())
                others.remove('fields')
                df = pd.DataFrame(columns=fields+others)
                for card in infos:
                    df.loc[int(card['cardId']), fields] = [a['value']
                                                           for a in card['fields'].values()]
                    df.loc[int(card['cardId']), others] = [card[a]
                                                           for a in others]
                df['Type'] = df['template'].apply(lambda x: x['name'])

                df['NotSeen'] = pd.Series(True, index=df.index)
                pkeys = list(self.players.keys())
                df[pkeys] = pd.DataFrame(False, columns=pkeys, index=df.index)
                self.all_words = df

                return df

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
                        'guiDeckOverview', val['ankiport'], name=self.deckname)
                    invoke('sync', val['ankiport'])
                    invoke(
                        'guiDeckOverview', val['ankiport'], name=self.deckname)

                    #  print(val['fn'])
                    query = '"deck:{}" (is:learn or prop:due<1)'.format(
                        self.deckname)
                    #  print(query)
                    val['ankiCards'] = invoke(
                        'findCards', val['ankiport'], query=query)
                    #  print(val['ankiCards'])
                    if result == None:
                        result = set(val['ankiCards'])
                    else:
                        result = result & set(val['ankiCards'])
                except KeyError:
                    print('KeyError')

            result = list(result)

            self.prepare_answers(cids=result)

            self.next_word()
            if self.check_if_game_done():
                self.end_game()

            thread = threading.Thread(target=self.timer)
            thread.start()

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
        print(str(pid) + ' ' + str(cid))
        if 'ankiport' in self.players[pid]:
            if invoke('areDue', self.players[pid]['ankiport'], cards=[cid])[0]:
                print('Answering  {} : {}'.format(pid, cid))
                invoke('answerCard', self.players[pid]
                       ['ankiport'], cid=cid, ease=ease)
                self.all_words[pid].loc[cid] = False
            else:
                print('Not Due so not answering {}:{}'.format(pid, cid))
        else:
            print('Player not anki {}:{}'.format(pid, cid))

    def answer(self, pid, answer):
        """
        Docstring
        """
        if self.is_right_answer(answer):
            self.players[pid]['points'] += 1
            cid = int(self.current_word.name)
            if 'ankiport' in self.players[pid]:
                self.anki_answer(pid, cid)
            else:
                self.all_words[pid].loc[cid] = False

            self.next_word()
            if self.check_if_game_done():
                self.end_game()
            return 1

        return 0

    def answer_audio(self, cid='', asquiz=False):
        if cid == None:
            cid = self.current_word.name

        val = self.all_words.loc[cid]
        port = '8766'
        src_audio = '/tmp/tellangsrc.mp3'
        dst_audio = '/tmp/tellangdst.mp3'
        out_audio = '/tmp/tellangout.mp3'
        first_silence = get_silence(6)
        second_silence = get_silence(3)
        eng_audio = dst_audio
        ja_audio = src_audio
        name = self.answer_str(cid)
        res = None
        if asquiz:
            if val['Type'] == 'Recall':
                eng_audio = src_audio
                ja_audio = dst_audio

            elif val['Type'] == 'Recognition':
                ja_audio = src_audio
                eng_audio = dst_audio

            if val['Audio']:
                encoded_audio = invoke('retrieveMediaFile',
                                       port, filename=val['Audio'][7:-1])
                # jap_audio
                with open(ja_audio, 'wb') as f:
                    f.write(base64.b64decode(encoded_audio))
            else:
                tts = gTTS(val['Expression'], lang='ja')
                tts.save(ja_audio)

            # eng_audio
            tts = gTTS(val['Meaning'], lang='en')
            tts.save(eng_audio)

            # concat
            returned_value = subprocess.call('ffmpeg -y -i "concat:{}|{}|{}|{}" -map_metadata -1 {}'.format(
                src_audio, first_silence, dst_audio, second_silence, out_audio), shell=True)  # returns the exit code in unix
        else:
            if val['Audio']:
                encoded_audio = invoke('retrieveMediaFile',
                                       port, filename=val['Audio'][7:-1])
                # jap_audio
                with open(ja_audio, 'wb') as f:
                    f.write(base64.b64decode(encoded_audio))
            else:
                tts = gTTS(val['Expression'], lang='ja')
                tts.save(ja_audio)

            returned_value = subprocess.call('ffmpeg -y -i  {} -map_metadata -1 -c:a copy {}'.format(
                src_audio, out_audio), shell=True)

        with open(out_audio, 'rb') as f:
            res = BytesIO(f.read())
        if val['Type'] == 'Recall':
            res.name = name

        elif val['Type'] == 'Recognition':
            res.name = val['Expression']

        return res
