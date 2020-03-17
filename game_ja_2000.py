#!/usr/bin/env python

from game import Game, State
from io import BytesIO
from helper import invoke, get_silence
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
import os


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
                df = df[df['Type'] != 'Reading']
                df['Expression'] = df['Expression'].apply(
                    lambda x: html2text(x))
                df['Meaning'] = df['Meaning'].apply(
                    lambda x: x.split('<br />')[0])
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
        first_silence = get_silence(10)
        first_silence_1 = get_silence(2)
        first_silence_2 = get_silence(6)
        second_silence = get_silence(3)
        eng_audio = ''
        ja_audio = ''
        name = self.answer_str(cid)
        res = None
        if asquiz:

            #  if val['Type'] == 'Reading':
            #  ja_audio = src_audio
            #  eng_audio = dst_audio

            if val['Type'] == 'Listening':
                ja_audio = src_audio
                eng_audio = dst_audio
                name = val['Expression']

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
            tts = gTTS(val['Meaning'], lang='en')
            tts.save(eng_audio)

            if val['Type'] == 'Listening':
                returned_value = subprocess.call('ffmpeg -y -i "concat:{}|{}|{}|{}|{}|{}" -map_metadata -1 {}'.format(
                    src_audio, first_silence_1, src_audio, first_silence_2, dst_audio, second_silence, out_audio), shell=True)  # returns the exit code in unix
            elif val['Type'] == 'Production':
                returned_value = subprocess.call('ffmpeg -y -i "concat:{}|{}|{}|{}" -map_metadata -1 {}'.format(
                    src_audio, first_silence, dst_audio, second_silence, out_audio), shell=True)  # returns the exit code in unix
            # concat
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
        res.name = name
        return res
