#!/usr/bin/env python

from game import Game, State
from io import BytesIO
from helper import invoke
import threading
import telegram
import subprocess
from datetime import datetime as dt
import time
import pandas as pd
from config import ANKIPORTS
from gtts import gTTS
import ast
import base64
from html2text import html2text


class Game_ja2000(Game):
    """
    Playes for kanji
    """

    def __init__(self):
        """TODO: Docstring for __init__.

        :f: TODO
        :returns: TODO

        """
        Game.__init__(self)
        self.deckname = "Nihongo::Japanese Core 2000 Step 01 Listening Sentence Vocab + Images"
        self.all_words = pd.DataFrame()
        self.current_word = None

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

    def add_player(self, user, with_anki=True):
        """
        Docstring
        """
        if user.id in self.players:
            if with_anki and (user.id in ANKIPORTS):
                self.players[user.id]['ankiport'] = ANKIPORTS[user.id]
            else:
                if 'ankiport' in self.players[user.id]:
                    del self.players[user.id]['ankiport']
            return 1
        self.players[user.id] = {'fn': user.first_name, 'ln': user.last_name,
                                 'points': 0}
        #  print(self.all_words.columns)
        self.all_words[user.id] = pd.Series(False, index=self.all_words.index)
        #  print(self.all_words.columns)

        try:
            if with_anki:
                self.players[user.id]['ankiport'] = ANKIPORTS[user.id]
        except KeyError:
            pass
        return 0

    def timer(self):
        """
        Docstring
        """
        while self.state == State.STARTED:
            delta = dt.now() - self.current_word_begin_time
            if delta.seconds > 0 and self.phase == 0:
                kanji = self.current_word['Expression']

                self.context.bot.send_message(chat_id=self.update.effective_chat.id,
                                              text='{}\n*{}*'.format(
                                                  self.status(), kanji),
                                              parse_mode=telegram.ParseMode.MARKDOWN)
                self.phase = 1 if (self.current_word['Type'] ==
                                   'Reading' and not self.current_word['Expression'] == self.current_word['Reading']) else 2
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
        cardinfo = self.current_word

        if cardinfo['Type'] == 'Reading':
            #  answers = [re.sub(r'\([^)]*\)', '', a).strip().lower()
            #  for a in ansval['Meaning'].replace(',', ';').replace('...', '').split(';')]
            answers = [cardinfo['Meaning']]
        elif cardinfo['Type'] == 'Production':
            answers = [cardinfo['Reading']]
        elif cardinfo['Type'] == 'Listening':
            answers = [cardinfo['Meaning']]

        return ans in answers

    def answer_str(self, cid=None):
        """TODO: Docstring for print_answer.
        :returns: TODO

        """
        if cid == None:
            cid = self.current_word.name
        self.all_words.loc[cid]
        df = self.all_words
        cardinfo = df.loc[cid]
        if cardinfo['Type'] == 'Reading':
            text = '%s : %s' % (cardinfo['Expression'], cardinfo['Meaning'])
        elif cardinfo['Type'] == 'Production':
            text = '%s : %s' % (cardinfo['Meaning'], cardinfo['Expression'])
        elif cardinfo['Type'] == 'Listening':
            text = '%s : %s' % (cardinfo['Expression'], cardinfo['Meaning'])
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
                df['Expression'] = df['Expression'].apply(lambda x: html2text(x))
                df['Meaning'] = df['Meaning'].apply(lambda x: x.split('<br />')[0])
                df['Reading'] = df['Reading'].apply(lambda x: html2text(x))

                df['NotSeen'] = pd.Series(True, index=df.index)
                pkeys = list(self.players.keys())
                df[pkeys] = pd.DataFrame(False, columns=pkeys, index=df.index)
                self.all_words = df

                return df

    def answer_audio(self, cid=None, asquiz=False):
        """TODO: Docstring for print_answer.
        :returns: TODO

        """
        if cid == None:
            cid = self.current_word.name

        val = self.all_words.loc[cid]
        port = '8766'
        src_audio = '/tmp/tellangsrc.mp3'
        dst_audio = '/tmp/tellangdst.mp3'
        out_audio = '/tmp/tellangout.mp3'
        ja_audio = src_audio
        if asquiz:
            name = self.answer_str(cid)

            res = []
            text = ''
            dummy_audio = '/tmp/dummy.mp3'
            lang = 'en'
            delay = 5

            subprocess.call('ffmpeg -y -f lavfi -i anullsrc -t {} '.format(delay) +
                            dummy_audio, shell=True)  # returns the exit code in unix
            eng_audio = ''
            ja_audio = ''

            if val['Type'] == 'Reading':
                ja_audio = src_audio
                eng_audio = dst_audio

            elif val['Type'] == 'Listening':
                ja_audio = src_audio
                eng_audio = dst_audio

            elif val['Type'] == 'Production':
                eng_audio = src_audio
                ja_audio = dst_audio

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
            tts = gTTS(val['Meaning'], lang=lang)
            tts.save(eng_audio)

            # concat
            returned_value = subprocess.call('ffmpeg -y -i "concat:{}|{}|{}" -map_metadata -1 {}'.format(
                src_audio, dummy_audio, dst_audio, out_audio), shell=True)  # returns the exit code in unix

            with open(out_audio, 'rb') as f:
                val['audioQuiz'] = BytesIO(f.read())
            print('Name '+name)
            val['audioQuiz'].name = name

            return val['audioQuiz']
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
            name = self.answer_str(cid)
            print(name)
            res.name = name
        return res

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

        elif self.state == State.STARTED:
            self.context.bot.send_message(chat_id=self.update.effective_chat.id,
                                          text="Game running")
        return 0

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
            cid = self.current_word.name
            if 'ankiport' in self.players[pid]:
                self.anki_answer(pid, cid)
            else:
                self.all_words[pid].loc[cid] = False

            self.next_word()
            if self.check_if_game_done():
                self.end_game()
            return 1

        return 0
