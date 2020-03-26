#!/usr/bin/env python

from game import Game
from io import BytesIO
from helper import invoke, get_silence
import subprocess
from gtts import gTTS
import base64


class Game_500(Game):
    """
    Playes for 500
    """

    def __init__(self):
        """TODO: Docstring for __init__.

        :f: TODO
        :returns: TODO

        """
        Game.__init__(self)
        self.deckname = "English::English First 500 - Green Yurt (mn)"
        self.deckfilter = ''

    def timer(self):
        """
        Docstring
        """
        pass

    def answer_str(self, cid=None):
        """TODO: Docstring for print_answer.
        :returns: TODO

        """
        if cid == None:
            cid = self.current_word.name
        df = self.all_words
        cardinfo = df.loc[cid]
        if cardinfo['Type'] == 'Recall':
            text = '%s : %s' % (cardinfo['Mongolian'], cardinfo['English'])
        elif cardinfo['Type'] == 'Recognition':
            text = '%s : %s' % (cardinfo['English'], cardinfo['Mongolian'])
        return text

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
        first_silence = get_silence(7)
        first_silence_1 = get_silence(2)
        first_silence_2 = get_silence(6)
        second_silence = get_silence(3)
        eng_audio = ''
        mn_audio = ''
        name = self.answer_str(cid)
        res = None
        if asquiz:

            #  if val['Type'] == 'Reading':
            #  mn_audio = src_audio
            #  eng_audio = dst_audio

            if val['Type'] == 'Recall':
                mn_audio = src_audio
                eng_audio = dst_audio

            elif val['Type'] == 'Recognition':
                eng_audio = src_audio
                mn_audio = dst_audio

            if val['Mongol_Audio']:
                encoded_audio = invoke('retrieveMediaFile',
                                       port, filename=val['Mongol_Audio'][7:-1])
                if type(encoded_audio) != str:
                    with open(out_audio, 'rb') as f:
                        res = BytesIO(f.read())
                    return res
                # jap_audio
                with open(mn_audio, 'wb') as f:
                    f.write(base64.b64decode(encoded_audio))
            else:
                tts = gTTS(val['Mongolian'], lang='ru')
                tts.save(mn_audio)

            # eng_audio
            if val['English_Audio']:
                encoded_audio = invoke('retrieveMediaFile',
                                       port, filename=val['English_Audio'][7:-1])
                if type(encoded_audio) != str:
                    with open(out_audio, 'rb') as f:
                        res = BytesIO(f.read())
                    return res
                # jap_audio
                with open(eng_audio, 'wb') as f:
                    f.write(base64.b64decode(encoded_audio))
            else:
                tts = gTTS(val['English'], lang='ru')
                tts.save(eng_audio)

            returned_value = subprocess.call('ffmpeg -y -i "concat:{}|{}|{}|{}|{}|{}" -map_metadata -1 {}'.format(
                src_audio, first_silence_1, src_audio, first_silence_2, dst_audio, second_silence, out_audio), shell=True)  # returns the exit code in unix
            # concat

        with open(out_audio, 'rb') as f:
            res = BytesIO(f.read())
        try:
            res.name = name
        except:
            print('no name '+str(val))

        return res
