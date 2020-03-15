#!/usr/bin/env python

from game import Game, State
from helper import invoke
import telegram
from datetime import datetime as dt
import time

from jiwer import wer

class English4000Game(Game):
    """
    Playes for kanji
    """
    def __init__(self):
        """TODO: Docstring for __init__.

        :f: TODO
        :returns: TODO

        """
        Game.__init__(self)
        self.deckname = "English::4000 Essential English Words"
        self.withaudio = False

    def timer(self):
        """
        Docstring
        """
        while self.state == State.STARTED:
            delta = dt.now() - self.current_word_begin_time
            if delta.seconds > 0 and self.phase == 0:
                self.context.bot.send_message(chat_id=self.update.effective_chat.id,
                                              text='{}\n*{}*'.format(
                                                  self.status(),
                                                  self.current_word['Mongolian']),
                                              parse_mode=telegram.ParseMode.MARKDOWN)
                self.phase = 1
            if delta.seconds > 40:
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
        ansval = self.current_word['Example']
        #  answers = [ansval['Example']]
        hyp = ' '.join([b for b in answer.lower()])
        right = ' '.join([b for b in ansval.lower()])
        #  answers = [re.sub(r'\([^)]*\)', '', a).strip().lower()
                   #  for a in ansval['keyword'].replace(',', ';').replace('...', '').split(';')]
        return wer(right, hyp) < 0.15

    def answer_str(self, cid=None):
        """TODO: Docstring for print_answer.
        :returns: TODO

        """
        if cid is None:
            cid = self.current_word.name
        df = self.all_words
        cardinfo = df.loc[cid]

        text = '%s : %s' % (cardinfo['Mongolian'], cardinfo['Example'])
        return text
