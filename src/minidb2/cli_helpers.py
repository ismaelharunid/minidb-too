# -*- coding: utf-8 -*-

# <minidb-too>/src/minidb2/cli_helpers.py



from collections.abc import Mapping, Sequence


class ChoiceQuery:

    AnswerEncaps = '(', ')'
    HotkeyEncaps = '[', ']'
    DefaultCase = str.capitalize

    @classmethod
    def extract_answers(cls, answers, start=0, stop=None, *,
                        answer_set=None):
        pos, endpos, _ = slice(start, stop, 1).indices(len(answers))
        if answer_set is None:
            answer_set = []

        # find answers if they're encapsulated
        if (encaps := cls.AnswerEncaps):
            if (left := encaps[0]):
                try:
                    pos = answers.index(left, pos, endpos) + len(left)
                except:
                    pass
            if (right := encaps[1]):
                try:
                    endpos = answers.index(right, pos, endpos)
                except:
                    pass

        # find separator
        sep = sorted((answers[pos:endpos].count(token), token)
                     for token in ',/|')[-1][1]

        # extract answers
        for ans in answers[pos:endpos].split(sep):
            ans = ans.strip()
            if not (ans in ('', 'or') or ans in answer_set):
                answer_set.append(ans)

        return answer_set

    @classmethod
    def clean_answers(cls, answers:list, default=None):
        answer_set = []
        hotkeys = {}
        encaps = cls.HotkeyEncaps
        for ans in answers:
            ans = ans.strip()
            if not ans: continue   # eliminate empties

            hk = None
            sp, ep = 0, len(ans)
            if encaps:
                try:
                    sp = ans.index(encaps[0], sp, ep)
                    p0 = sp + len(encaps[0])
                except:
                    pass
                else:
                    try:
                        p1 = ans.index(encaps[1], p0, ep)
                        ep = p1 + len(encaps[1])
                    except:
                        pass
                    else:
                        if sp < p0 or p1 < ep:
                            hk = ans[p0:p1]
                            ans = ans[:sp] + hk + ans[ep:]
                            #print(hk, ans)

            # eliminate casing
            if not ans: continue   # eliminate empties
            ians = ans.lower()

            if hk:
                # we have a hotkey, so register it
                if hk in hotkeys and hotkeys[hk] != ians:
                    raise ValueError('Hotkey {!r} collision, previous {!r},'
                                     ' current {!r}'
                                     .format(hk, hotkeys[hk], ians))
                hotkeys[hk] = ians

            if default is None and ans != ians:
                default = ians

            answer_set.append( ians )

        #print('hotkeys', hotkeys)
        return (answer_set, default, hotkeys)

    prompt = None
    answers = None
    default = None   # empty -> this
    hotkeys = None
    reject = None
    accept = None
    failure = None
    persistent = None
    previous = None
    max_tries = None

    def __new__(cls, answers, default=None, *,
                prompt=None, reject=None, accept=None, failure=None,
                hotkeys=None, persistent=None, max_tries=None):
        # pre-process and validate answers and prompt
        if not answers:
            answer_set = ()
        elif isinstance(answers, str):
            if prompt is None:
                # answers is prompt with embedded answers)
                prompt = answers
            answer_set = cls.extract_answers(answers)
        elif not (isinstance(answers, Sequence)
                  and all(i and isinstance(i, str) for i in Sequence)):
            raise TypeError('answers expects a str or Sequence[str], not {!r}'
                            .format(answers))
        else:
            answer_set = answers

        # clean answer_set and grab potential default answer
        answer_set, default, hkeys = cls.clean_answers(answer_set, default)
        if hotkeys is None:
            hotkeys = hkeys
        elif isinstance(hotkeys, Mapping):
            # validate hotkeys
            for hk, ans in hotkeys.items():
                if ans not in answer_set:
                    raise ValueError('Hotkey {!r} for undefined answer {!r}'
                                     .format(hk, ans))
        else:
            raise ValueError('hotkeys expects a mapping, not {!r}'
                             .format(hotkeys))

        # create prompt if it wasn't given
        if not (not prompt or isinstance(prompt, str)):
            raise TypeError('prompt expects a non-empty str, not {!r}'
                            .format(prompt))

        # validate accept
        if not (not accept
                or callable(accept)
                or isinstance(accept, str)
                or (isinstance(accept, Mapping)
                    and all(k and isinstance(k, str)
                            and (v is None
                                 or callable(v)
                                 or isinstance(v, str))
                            for k, v in accept.items()))):
            raise ValueError('accept expects a callable, str or empty,'
                             ' not {!r}'.format(accept))

        # validate reject
        if not (callable(reject) or isinstance(reject, str) or not reject):
            raise ValueError('reject expects a callable, str or empty,'
                             ' not {!r}'.format(reject))

        # validate failure
        if not (callable(failure) or isinstance(failure, str) or not failure):
            raise ValueError('failure expects a callable, str or empty,'
                             ' not {!r}'.format(failure))

        # validate persistent
        if persistent:
            if isinstance(persistent, str):
                persistent = persistent.split()
            persistent = tuple(ans for ans in (i.strip() for i in persistent)
                               if ans)
            for ans in answer_set:
                if ans not in answer_set:
                    raise KeyError('persistant {!r} is not an answer'
                                   .format(ans))

        # validate max_trues
        if not (not max_tries
                or (isinstance(max_tries, int) and max_tries > 0)):
            raise ValueError('max_tries expects an uint or empty,'
                             ' not {!r}'.format(max_tries))


        self = super().__new__(cls)
        self.answers = tuple(answer_set)
        self.default = default or None
        self.hotkeys = hotkeys or {}
        self.accept = accept or None
        self.reject = reject or None
        self.failure = failure or None
        self.persistent = persistent or ()
        self.previous = None
        self.max_tries = max_tries or None

        self.prompt = (self.built_prompt(answer_set)
                       if prompt is None else
                       prompt)

        return self

    def __call__(self, prompt=None, default=None):
        return self.query(prompt, default=default)

    def built_prompt(self, sep='/', *,
                     answer_encaps=None,
                     answer_formatter=None,
                     hotkey_encaps=None):
        cls = type(self)
        if answer_encaps is None:
            answer_encaps = cls.AnswerEncaps
        if answer_formatter is None:
            answer_formatter = cls.DefaultCase
        if hotkey_encaps is None:
            hotkey_encaps = cls.HotkeyEncaps

        ansleft, ansright = (('', '') if answer_encaps else answer_encaps)
        hkleft, hkright = (('', '') if hotkey_encaps else hotkey_encaps)

        items = []
        for ans in self.answers:
            if self.default and answer_formatter and ans == self.default:
                ans = answer_formatter(ans)
            if self.hotkeys:
                for hk, hkans in self.hotkeys.items():
                    if hkans == ans:
                        try:
                            i = ans.lower().index(hk.lower())
                        except:
                            i = len(ans)
                        ans = ans[:i] + hkleft + hk + hkright + ans[i+1:]
            items.append( ans )

        if ' ' in sep:
            prompt = sep.join(items[:-1])
            if len(items) > 1:
                prompt += ' or ' + items[-1]
        else:
            prompt = sep.join(items)
        prompt = ansleft + prompt + ansright

        return prompt

    def query(self, prompt=None, *,
              default=None, accept=None, reject=None):
        if default is None:
            default = self.default
        default_withbs = (default or '')
        default_withbs += '\b' * len(default_withbs)

        if prompt is None:
            prompt = self.prompt
        prompt = prompt.format(default=default or '',
                               default_withbs=default_withbs)

        answer, num_tries = self.previous, 0
        while self.max_tries is None or num_tries < self.max_tries:
            if answer is None:
                answer = (input(prompt) or default or '')
                answer = self.hotkeys.get(answer, answer).lower()
                num_tries += 1

            if answer:
                n = len(answer)
                for ans in self.answers:
                    if ans[:n] == answer:
                        answer = ans
                        break
                else:
                    if self.reject:
                        if callable(self.reject):
                            self.reject(self, answer)
                        elif isinstance(self.reject, str):
                            print(self.reject.format(num_tries=num_tries,
                                                     answer=answer))
                    if reject:
                        if callable(reject):
                            reject(self, answer)
                        elif isinstance(reject, str):
                            print(reject.format(num_tries=num_tries,
                                                answer=answer))
                    answer = None
                    continue

                if callable(self.accept):
                    if (resp := self.accept(self, answer)) is False:
                        answer = None
                        continue
                    elif resp and isinstance(resp, str):
                        answer = resp
                elif self.accept and isinstance(self.accept, str):
                    print(self.self.accept.format(num_tries=num_tries,
                                                  answer=answer))
                elif (isinstance(self.accept, Mapping)
                      and answer in self.accept):
                    if callable(self.accept[answer]):
                        if (resp := self.accept[answer](self, answer)) is False:
                            answer = None
                            continue
                        elif resp and isinstance(resp, str):
                            answer = resp
                    elif isinstance(self.accept[answer], str):
                        print(self.accept[answer].format(num_tries=num_tries,
                                                 answer=answer))

                if callable(accept):
                    if (resp := accept(self, answer)) is False:
                        answer = None
                        continue
                    elif resp and isinstance(resp, str):
                        answer = resp
                elif accept and isinstance(accept, str):
                    print(self.accept.format(num_tries=num_tries,
                                             answer=answer))
                elif isinstance(accept, Mapping) and answer in accept:
                    accept = accept[answer]
                    if callable(accept):
                        if (resp := accept(self, answer)) is False:
                            answer = None
                            continue
                        elif resp and isinstance(resp, str):
                            answer = resp
                    elif isinstance(accept, str):
                        print(accept.format(num_tries=num_tries,
                                            answer=answer))

                # we got a valid answer, see if it's persistent
                if answer in self.persistent:
                    self.previous = answer

                # return valid answer
                return answer

            #END: while max_tries is None or num_tries < max_tries
            answer = None

        if self.failure:
            self.failure(self, answer)

        return None


