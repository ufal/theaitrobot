#!/usr/bin/env python3
# coding: utf-8

"""
Backend for interactive GPT2 story generation.
"""

from   argparse import ArgumentParser
import datetime
import multiprocessing
import os
import queue
import re
import string
import sys
import threading
import time
import traceback
import json
from   typing import Iterable, Optional, Tuple

import dataset
import flask
from   keyops import compress_key, expand_key, validate_key, split_into_parts
import logging
from   logzero import logger, loglevel
import numpy as np
import random
import torch
from   torch import Tensor
from   torch.nn import functional as F
from   transformers import AutoTokenizer, AutoModelForCausalLM
import unidecode  # noqa: E402

from   char_support import trie, build_trie, extract_character_names
import git_util
from   keyops import compress_key
import summarize
import urutranslate  # noqa: E402
from nli import NLI

import langid
langid.set_languages(['en', 'cs'])

SERVER_VERSION = '2022-06-20'   # XXX update manually on major changes to this script


LOGO='''

****** **  ** ******         ** ****** *****  ******
****** **  ** ******         ** ****** ****** ******
  **   **  ** **                  **   **  ** **
  **   ****** ******  ****  ***   **   ****** ******
  **   ****** ******     **  **   **   *****  ******
  **   **  ** **      *****  **   **   ** **  **
  **   **  ** ****** **  **  **   **   **  ** ******
  **   **  ** ******  ***** ****  **   **  ** ******

'''

FORBIDDEN_LINES_MAX_RETRIES = 10

NLI_THRESHOLD = 0.40
UNBREAKING = re.compile(r".*(\s[A-Z]|v|vs|i\.e|rev|e\.g|Adj|Adm|Adv|Asst|Bart|Bldg|Brig|Bros|Capt|Cmdr|Col|Comdr|Con|Corp|Cpl|DR|Dr|Drs|Ens|Gen|Gov|Hon|Hr|Hosp|Insp|Lt|MM|MR|MRS|MS|Maj|Messrs|Mlle|Mme|Mr|Mrs|Ms|Msgr|Op|Ord|Pfc|Ph|Prof|Pvt|Rep|Reps|Res|Rev|Rt|Sen|Sens|Sfc|Sgt|Sr|St|Supt|Surg)\.\s*")

GEN_PARAMS = {
        'temperature': 1.0,
        'top_p': 0.9,
        'repetition_penalty': 1.2,
        'top_k': 50,
        'do_sample': True,
        'typical_p': 0.2,
        }

FORBIDDEN_LINES_WINDOW = 4
EOT = '<|endoftext|>'

# This char means cutting:
# abcd2_ef ... cut the 2nd line from start, 0-based (i.e. 'c': 'ab def')
CUT = '_'

# This means adding before the specified position:
# abcdef3. ... after acb add a line (i.e. abcadef while keeping original def)
ADD = '.'

# Regenerate the given line
REG = '~'

def set_seed(scene_key):
    if '-' in scene_key:
        _, scene_key = scene_key.split('-', 1)
    random.seed(scene_key)
    seed = random.getrandbits(32)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.device_count() >=1:
        torch.cuda.manual_seed_all(seed)

    logger.info('GPT2: Set random seed for {}: {}'.format(compress_key(scene_key), seed))

def smart_random(x):
    num = random.random() * (2**x - 1) / 10.0
    logger.info('Generating smart random with result {}'.format(num))
    return num

BRACKETED = re.compile(r'^[\[\(].*[\]\)]$')

def looks_scenic(line, is_continuation=False):
    """Does this line look like a scenic remark?

    Peter: [looks into his bag]

    Known limitation: false positive for:
    Peter: (smilingly) I have something for you (pointing his gun)

    is_continuation: This is a continuation line following a line with a
    character name; in this case we do not require the line to contrain a
    colon not to be considered scenic."""

    if BRACKETED.match(line.strip()):
        # [A scenic remark.]
        return True
    elif not is_continuation:
        if ':' in line:
            # Name: line
            _, line = line.split(':', 1)
            return bool(BRACKETED.match(line.strip()))
        else:
            # no colon: looks scenic
            return True
    else:
        # Is not bracketed like a scenic remark,
        # and is a continuation line so we do not reuquire a colon.
        return False

def shorten_string(text, maxlen=50):
    if len(text) < maxlen:
        return text
    else:
        half = int(maxlen/2)
        return text[:half] + '...' + text[-half:]

# Predict all tokens
#with torch.no_grad():
#    outputs = model(tokens_tensor)
#    predictions = outputs[0]

# get the predicted next sub-word (in our case, the word 'man')
#predicted_index = torch.argmax(predictions[0, -1, :]).item()
#predicted_text = tokenizer.decode(indexed_tokens + [predicted_index])
#assert predicted_text == 'Who was Jim Henson? Jim Henson was a man'

class GenerateEOL(Exception):
    def __init__(self, ids):
        self.ids = ids

class GenerateEOSentence(Exception):
    def __init__(self, ids):
        self.ids = ids

class Generator(multiprocessing.Process):
    """Slave process, handles GPT2, generates stuff on demand.

       Parameter self.max_len needs to be set after initialization.

    """

    def __init__(self, conn, model, gen_num, summarize=False, log_level=logging.DEBUG, ban_remarks=True, prose=False, use_nli=False):
        super(Generator, self).__init__()
        self.conn = conn
        self.model_name = model
        self.gen_num = gen_num
        self.summarize = summarize
        self.log_level = log_level
        # number of tokens to summarize
        self.start_from = 0
        self.ban_remarks = ban_remarks
        self.prose = False
        self.nli = None
        self.sentences = []

        if use_nli:
            self.nli = NLI()

    def generate(self, context, params):
        return self.model.generate(
                    tokenizer=self.tokenizer,
                    input_ids=context,
                    max_length=self.max_len,
                    **params
                    )

    def postprocess(self, line):
        line = line.rstrip()
        if self.prose:
            # We are generating a synopsis so we want no colons!
            # Colons are legal and nice and everything, but we use them as
            # special characters that separate character name and character
            # line, so having them in synopsis lines may break various things.
            # A semicolon should probably mostly be OKish instead on a colon.
            line = line.replace(':', ';')
        return line

    def get_nli_score(self, ids):
        if self.prose:
            output_sequence = ids[self.start_from:]
            input_sequence = ids[:self.start_from]
            decoded_output = self.tokenizer.decode(output_sequence)
            decoded_input = self.tokenizer.decode(input_sequence)
            return self.nli.get_single_nli_score(decoded_input, decoded_output)
        else:
            # We work with decoded_all, because this might not be the first sentence in a speaker's utterance
            # Therefore, in order to get the speaker information, we need to be sure to access the last generated line
            decoded_all = self.tokenizer.decode(ids)
            split_lines = re.split('\n+', decoded_all)
            speaker = re.sub(r':.*', '', split_lines[-1])
            # If there is no speaker, it is probably a scenic remark which should not be NLI'd
            if len(speaker) > 1:
                decoded_output = self.tokenizer.decode(ids[self.start_from:])
                decoded_output = re.sub(r'[^:]+:\s*', '', decoded_output)
                filtered_lines = []
                for line in split_lines:
                    if line.strip().startswith(speaker):
                        # Only add the utterances of the current speaker
                        utterance = re.sub(r'[^:]+:\s*', '', line).strip()
                        if not utterance.endswith('.') and not utterance.endswith('?') and not utterance.endswith('!'):
                            utterance += '.'
                        filtered_lines.append(utterance)
                nli_context = " ".join(filtered_lines)
                if nli_context.endswith(decoded_output):
                    nli_context = nli_context[:-len(decoded_output)].strip()
                #nli_context = nli_context.removesuffix(decoded_output)
                return self.nli.get_single_nli_score(nli_context, decoded_output)
        # This will happen for scenic remarks, for the time being let them be
        return 1

    # TODO: reintroduce character manipulation; maybe list allowed characters,
    # maybe list forbidden characters (but do something like that);
    # maybe let the model generate and then decide if the character is OK, or
    # maybe predecide which character should speak (and add it to input)
    def gen_lines(self, prompt, scene_key, characters=None,
            limit_characters=True, forbidden_lines=[], outline_kit=(None, 0)):
        """This is where the generation occurs -- generate self.gen_num continuation
        alternatives for the given prompt.
        prompt = input text
        scene_key = prompt_key-cont_key -- e.g. life-aac will generate
        life-aac (and possibly life-aacaaaa...); will determine random seed
        forbidden_lines = lines that must not be generated (stripped)
        characters = list of character names allowed in generation; empty =
        generate any character names
        outline_kit = the data necessary for (potentially) adding a scenic remark, tuple (string, int)
        returns a list of generated lines; the first line corresponds to the
        input scene_key, the further lines corrspond to "...a" continuations
        in case a remark is inserted, it is present in the list
        """

        # based on stuff from interactive.py
        logger.info('GENERATOR: starting {}'.format(
            repr(shorten_string(prompt))))
        gen_len = 100
        context = self.tokenizer.encode(prompt)

        if self.summarize and len(context) >= ( self.max_len - gen_len):
            before_summ_length = len(context)
            summarized = summarize.summarize_dialogue(prompt,n_lines=10)
            if summarized.endswith(': '):
                summarized = summarized[:-1]
            context    = self.tokenizer.encode(summarized)
            logger.info(f"SUMMARIZER: summarized  {repr(prompt)} tokens into => \n {repr(summarized)}.")

        if prompt.endswith(':'):
            # This looks like a character name, let's keep it on one line
            is_continuation = True
        else:
            # newline token_id hardcoded
            context += [self.NL]
            is_continuation = False


        prompt_lines = [x for x in prompt.split('\n') if x]
        last_prompt_line = prompt_lines[-1] if prompt_lines else ''

        next_remark_string, lines_since_remark = outline_kit
        if next_remark_string and next_remark_string not in forbidden_lines and smart_random(lines_since_remark) > 0.6:
            # The remark should start with an empty line, but we need to add
            # it manually so that the encoder does not eat it up.
            # It should also end with a newline but this is not stored in
            # the database so we only add it to the encded variant.
            logger.info('GENERATOR: adding scenic remark {}'.format(
                repr(next_remark_string)))
            context += [self.NL] + self.tokenizer.encode(next_remark_string) + [self.NL]
            next_remark_string = '\n' + next_remark_string
        else:
            next_remark_string = None # If we don't use it, we don't want to save it into db

        context = context[- self.max_len + gen_len:]

        self.start_from = len(context)
        context = torch.tensor([context])
        if torch.cuda.device_count() >= 1:
            context = context.to('cuda')

        # NOTE: currently not used!
        if limit_characters:
            if characters is None:
                characters = extract_character_names(prompt)

        # returns a list of lines starting with line scene_key

        set_seed(scene_key)

        line_ok = False
        retries = 0
        self.sentences = []
        while not line_ok and retries < FORBIDDEN_LINES_MAX_RETRIES and self.start_from <= self.max_len - gen_len:
            nli_ok = True
            is_eol = False
            try:
                output_sequence = self.generate(context, GEN_PARAMS)[0][self.start_from:]
                # If we want NLI to check the last sentence even before the generator stops without an exception, uncomment this
                #nli_score = self.get_nli_score(output_sequences[0])
                #if nli_score < NLI_THRESHOLD:
                    #nli_ok = False

            # When a line is generated, GenerateEOL is raised, terminating
            # model.generate(), containing the IDs of the generated tokens.
            except GenerateEOL as g:
                is_eol = True
                output_sequence = g.ids[0][self.start_from:]
                nli_score = self.get_nli_score(g.ids[0])
                if nli_score < NLI_THRESHOLD:
                    nli_ok = False
            except GenerateEOSentence as g:
                output_sequence = g.ids[0][self.start_from:]
                nli_score = self.get_nli_score(g.ids[0])
                if nli_score < NLI_THRESHOLD:
                    nli_ok = False

            #TODO what if no exception is raised?

            logger.debug("OUT_S:" + str(output_sequence))

            output_line = self.postprocess(self.tokenizer.decode(output_sequence))
            logger.debug("OUT_L:" + repr(output_line))

            # TODO: maybe forbid even very similar lines e.g. using
            # some Levenshtein?
            is_forbidden = output_line.strip() in forbidden_lines
            is_banned_scenic_remark = len(self.sentences) == 0 and self.ban_remarks and looks_scenic(output_line, is_continuation) and looks_scenic(last_prompt_line)

            if not is_forbidden and not is_banned_scenic_remark and nli_ok:
                self.sentences.append(output_line)
                if len(self.sentences) >= 5 or is_eol:
                    line_ok = True
                else:
                    context = torch.cat((context[0], output_sequence)).unsqueeze(0)
                    self.start_from = len(context[0])
            elif is_banned_scenic_remark:
                logger.info("Line contains a banned scenic remark on retry {}".format(retries))
                retries += 1
            elif not nli_ok:
                logger.info("Line has a too low NLI score on retry {}".format(retries))
                retries += 1
            else:
                logger.info("Line is forbidden on retry {}".format(retries))
                retries += 1

        if self.sentences:
            output_line = "".join(self.sentences)

        logger.info('GENERATOR truncated {}: {}'.format(
            compress_key(scene_key), repr(shorten_string(output_line))))

        # TODO the outer method should accept the list of lines and store them all in DB
        if next_remark_string:
            lines = [next_remark_string, output_line]
        else:
            lines = [output_line]

        return {'lines': lines,
                'model': self.model_name}


    def run(self):
        """Initialize GPT2 (must be done within the slave process) and wait for input."""
        # set logging level for the slave process
        loglevel(self.log_level)

        logger.info('GENERATOR: Loading model ' + self.model_name)

        # Load pre-trained model (weights)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(self.model_name)

        # Set the model in evaluation mode to deactivate the DropOut modules
        # This is IMPORTANT to have reproducible results during evaluation!
        self.model.eval()

        # If you have a GPU, put everything on cuda
        if torch.cuda.device_count()>=1:
            self.model.to('cuda')

        self.max_len = self.tokenizer.max_model_input_sizes[self.model.config.model_type]

        # We want model.generate() to return when it generates a line (i.e.
        # some non-white-space followed by a newline),
        # but we do not want to modify model.generate() directly.
        # Instead, we hack our way into model.generate() by replacing
        # model.prepare_inputs_for_generation() (which is called each time a
        # token is generated) by our wrapper, which terminates generate() by
        # raising a GenerateEOL exception once a line is generated.
        # When calling model.generate(), we catch this exception, interpret it
        # as a line having been generated, and extract the generated tokens
        # from it.

        # 1. Store the original prepare_inputs_for_generation()
        old_prep = self.model.prepare_inputs_for_generation

        # GPT2 has also e.g. '\n\n' as one token, so to check whether the last
        # token is a newline we actually check whether the last token
        # _contains_ a newline.
        def is_newline(decoded_id):
            return '\n' in decoded_id

        def is_end_of_sentence(decoded_ids):
            decoded_id = decoded_ids[-1]
            relevant_to_regex_check = decoded_ids[-9:] #9 because 6 is the highest len, and space before and dot after are mandatory
            if '.' in decoded_id:
                logger.info(f"Found ., checking for unbreaking in the relevant substring '{relevant_to_regex_check}' of the string '{decoded_ids}'")
                if UNBREAKING.match(relevant_to_regex_check):
                    return False
                else:
                    logger.info("Unbreaking not found")
            return '.' in decoded_id or '?' in decoded_id or '!' in decoded_id or ';' in decoded_id

        # 2. Create our wrapper for prepare_inputs_for_generation()
        def new_prep(input_ids, **model_kwargs):

            # Terminate by raising GenerateEOL if a line has been generated,
            # i.e. some non-white-space tokens have been generated and the
            # last token is a newline.
            if len(input_ids[0]) > self.start_from:
                decoded_ids = self.tokenizer.decode(input_ids[0][self.start_from:])
                # We only want to analyze sentences in summaries
                if self.nli and is_end_of_sentence(decoded_ids):
                    raise GenerateEOSentence(input_ids)
                if len(decoded_ids.strip()) > 0 or self.sentences:
                    if is_newline(decoded_ids[-1]):
                        # Terminates model.generate() and contains the generated
                        # tokens IDs
                        raise GenerateEOL(input_ids)

            # Otherwise, invoke the original prepare_inputs_for_generation()
            return old_prep(input_ids, **model_kwargs)

        # 3. Replace the original prepare_inputs_for_generation() with our
        # wrapper.
        self.model.prepare_inputs_for_generation = new_prep

        # GPT2 tokenizer eats whitespace at the boundaries, so we need to put
        # the newline between some other text to get its token code
        self.NL = self.tokenizer.encode('x\nx')[1]

        logger.info("GENERATOR: Model loaded.")

        # handle requests for generation
        while True:  # TODO do we need to end gracefully?
            prompt, scene_key, forbidden_lines, outline_kit = self.conn.recv()
            try:
                result = self.gen_lines(prompt, scene_key, forbidden_lines=forbidden_lines, outline_kit=outline_kit)
            except Exception as e:
                logger.exception('GENERATOR ERROR: {}'.format(e))
                result = {'error': str(e)}
            self.conn.send(result)


class Server:
    """Flask-based HTTP server, handling requests, getting stuff from DB & passing requests
    to the Generator."""

    def __init__(self, conn, db_file, gen_num, translate, as_console, outlines):
        self.lock = threading.Lock()
        self.conn = conn

        # remember if we're running as a real server, or from the console (i.e. no flask)
        self.as_console = as_console

        # Autoinsert lines from outline
        # NOTE: Used to be turned on by default,
        # now turned off by default
        self.outlines = outlines

        # requests and results
        self.generate_queue = queue.Queue()
        self.pregenerate_queue = queue.LifoQueue()
        self.results = dict()

        self.gen_num = gen_num
        self.db = dataset.connect('sqlite:///' + db_file, engine_kwargs={'connect_args': {'timeout': 60}})
        self.server_version = SERVER_VERSION
        script_dir = os.path.dirname(os.path.realpath(__file__))

        self.deployuser = "unknown deploy user"
        self.deploypath = "unknown deploy path"
        self.git_version = "outside a git repo"
        self.git_branch = "outside a git repo"
        try:
            with open('server.deployed') as deployinfo:
                line = deployinfo.read()
                self.deployuser, self.deploypath, self.git_version, self.git_branch, *_ = line.split()
        except Exception as e:
            logger.info('Cannot read file server.deployed: {}'.format(e))
            try:
                self.git_version = git_util.get_git_version(script_dir)
                self.git_branch = git_util.get_git_branch(script_dir)
            except Exception:
                pass
        self.translate = translate
        logger.info('{}Running server version {} {} {} deployed by {} from {}\n'.format(
                    LOGO, self.server_version, self.git_version, self.git_branch,
                    self.deployuser, self.deploypath))

        # start background thread for queue processing
        self.queue_thread_should_run = True
        self.queue_thread = threading.Thread(target=self.process_queues)
        self.queue_thread.start()

    def process_queues(self):
        while self.queue_thread_should_run:
            scene_key = None
            event = None
            pre = ''

            # block for 5 secs at most, then check whether we haven't been killed
            try:
                if not self.generate_queue.empty():
                    scene_key, prompt, prepend, event, forbidden_lines, outline_kit = self.generate_queue.get(True, 5)
                    pre = ''
                elif not self.pregenerate_queue.empty():
                    scene_key, prompt, prepend, event, forbidden_lines, outline_kit = self.pregenerate_queue.get(True, 5)
                    pre = 'pre'
            except queue.Empty:
                time.sleep(1)
                continue

            if scene_key:
                # recheck if key still not generated
                if scene_key in self.results:
                    # already generated
                    logger.info(f'SERVER: not {pre}generating {compress_key(scene_key)}, already generated')
                    if event:
                        event.set()

                else:
                    logger.info(f'SERVER: {pre}generating {compress_key(scene_key)}')

                    self.conn.send((prompt + prepend, scene_key, forbidden_lines, outline_kit))
                    result = self.conn.recv()
                    result_ok = 'lines' in result

                    if result_ok:
                        logger.info(f'SERVER: {pre}generated {compress_key(scene_key)}')
                        self.results[scene_key] = None
                        x = threading.Thread(target=self.store_result,
                                             args=(scene_key, result, prepend, event))
                        x.start()
                    else:
                        errormsg = str(result.get('error'))
                        logger.error(f'SERVER: failed to {pre}generate {compress_key(scene_key)}: {errormsg}')

                    logger.info('generate_queue: {} items; pregenerate_queue: {} items'.format(
                        self.generate_queue.qsize(), self.pregenerate_queue.qsize()))

            else:
                time.sleep(1)
                # TODO wait somehow in a clever way -- wait on some object for
                # max 10s, and whoever adds something to the queues notifies
                # this object

    def store_new_scene(self, scene_key, scene_prompt, username='',
            scene_outline=None, char1=None, char2=None):
        """Store a new scene in the DB."""
        logger.info(f'SERVER: storing scene {scene_key}...')
        prompt = scene_prompt.replace("\r\n", "\n").strip()
        # normalize scene key: strip accents, dashes to underscores, remove any non-standard characters
        scene_key = unidecode.unidecode(scene_key)
        scene_key = re.sub(r'[-–— ]', '_', scene_key)
        scene_key = re.sub(r'[^a-zA-Z0-9_]', '', scene_key)
        if scene_outline is not None:
            scene_outline = scene_outline.strip()
        scene = {'key': scene_key,
                 'prompt': prompt,
                 'outline': scene_outline,
                 'char1': char1,
                 'char2': char2,
                 'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 'username': username}
        # source language can be en or cs
        source_language = langid.classify(scene_prompt)[0] if scene_prompt else 'en'
        logger.info(f'SERVER: guessed source language as {source_language}')
        if source_language == 'cs':
            scene['cs_prompt'] = prompt
            scene['cs_outline'] = scene_outline
            if self.translate:
                scene['prompt'] = urutranslate.translate_with_roles_separately(
                        prompt, 'cs', 'en')
                if char1:
                    scene['char1'] = urutranslate.translate_role(
                            char1, 'cs', 'en')
                if char2:
                    scene['char2'] = urutranslate.translate_role(
                            char2, 'cs', 'en')
                if scene_outline:
                    scene['outline'] = urutranslate.translate_with_roles_separately(
                            scene_outline, 'cs', 'en')
        else:
            assert source_language == 'en'
            if self.translate:
                scene['cs_prompt'] = urutranslate.translate_with_roles_separately(
                        prompt)
                if scene_outline:
                    scene['cs_outline'] = urutranslate.translate_with_roles_separately(
                            scene_outline)
        self.lock.acquire()
        self.db.begin()
        # store & add a number at the end if the scene exists
        add_num = 0
        result = self.db['scenes'].insert_ignore(scene, ['key'])
        while not result and add_num < 1000:
            add_num += 1
            scene['key'] = scene_key + '_%d' % add_num
            result = self.db['scenes'].insert_ignore(scene, ['key'])
        self.db.commit()
        self.lock.release()
        if not result:
            raise Exception('Too many entries with the same name')
        return {'key': scene['key']}

    def store_human_input(self, key, human_input, input_type='human'):
        """Store a human-input line in the DB."""
        human_input = human_input.replace("\r\n", "\n").rstrip()
        logger.info(f'SERVER: storing human input at {compress_key(key)} of type {input_type}: {repr(human_input)}')
        data = {'text': human_input,
                'model': input_type,
                'server_version': self.server_version,
                'git_version': self.git_version,
                'git_branch': self.git_branch,
                'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self.lock.acquire()
        self.db.begin()
        letters = string.ascii_uppercase
        result = False
        while not result and letters:
            data['key'] = key + letters[0]
            letters = letters[1:]
            result = self.db['lines'].insert_ignore(data, ['key'])
        self.db.commit()
        self.lock.release()
        if not result:
            raise Exception('Too many human entries at this point')
        logger.info(f'SERVER: key = {data["key"]}')
        return {'key': data['key']}

    def join_prompt_and_lines(self, prompt, lines, char1=None, char2=None):
        """Prepare input prompt for GPT2 by joining together the scene prompt
        and the already generated lines.

        Joined by newlines by default, except
        for empty lines (which are cut lines and are skipped)
        and partial lines containing only character name and colon (e.g.
        'Man:'), which are joined with the subsequent line directly so as to
        form one input line instead of two; because the input for generation
        ends with the colon, the expectation is that the next line starts with
        a space, so no space is explicitly added here."""

        prepend_char = ''
        if len(lines) == 0 and char1:
            # force char1
            if prompt:
                prepend_char = f'\n{char1}:'
            else:
                prepend_char = f'{char1}:'
        elif len(lines) == 1 and char2:
            # force char2
            prepend_char = f'\n{char2}:'
        elif char1 and char2:
            # first two lines already generated AND both character names
            # specified -> force the character that did not say the last line
            if lines[-1].strip().startswith(char2):
                # force char1
                prepend_char = f'\n{char1}:'
            else:
                # force char2
                prepend_char = f'\n{char2}:'

        lines = [prompt] + lines
        lines_and_whitespace = []
        for line in lines[:-1]:
            if line:
                lines_and_whitespace.append(line)
                if not line.endswith(':'):
                    lines_and_whitespace.append('\n')
        # No whitespace at the end because the GPT2 tokenizer would eat it;
        # a final newline is added to end of input in gen_lines() if needed.
        if lines[-1]:
            lines_and_whitespace.append(lines[-1])
        return ''.join(lines_and_whitespace), prepend_char

    # generate a new line; return line, cs_line
    def generate_line(self, cur_scene_key, cur_lines, forbidden_lines, outline_text, pregenerate, prepend=''):
        pre = 'pre' if pregenerate else ''

        # Skip generation if endoftext already generated
        if EOT in cur_lines:
            self.store_empty_line(cur_scene_key)
            return '', ''
        else:
            lines = [line.strip() for line in cur_lines.split('\n') if line.strip()]

            # Forbidden lines, i.e. lines that the generator is
            # forbidden to produce at this step.
            # We also forbid last FORBIDDEN_LINES_WINDOW lines
            forbidden_lines = forbidden_lines.copy()
            for prev_line in lines[-FORBIDDEN_LINES_WINDOW:]:
                forbidden_lines.append(prev_line)

            # TODO make this prettier
            next_remark_string = None
            lines_since_remark = 0

            if outline_text and self.outlines:
                logger.debug('Outline is "{}"'.format(outline_text))
                outline = ['[' + o.strip() + ']' for o in outline_text.split('\n')]
                logger.debug('Outline is "{}"'.format(outline))
                i = 0
                j = 0
                # We don't need to count lines_since_remark if there are no more remarks to add
                while j < len(lines) and i < len(outline):
                    if outline[i] == lines[j].strip():
                        # The i-th line from outline was inserted here
                        i += 1
                        lines_since_remark = 0
                    elif looks_scenic(lines[j]):
                        # A scenic remark was generated here by GPT2
                        lines_since_remark = 0
                    else:
                        # A standard line was generated here by GPT2
                        lines_since_remark += 1
                    j += 1

                if i < len(outline):
                    next_remark_string = outline[i]

            logger.info('SERVER: queueing to {}generate {}'.format(pre, compress_key(cur_scene_key)))
            event = threading.Event()
            queue_item = (cur_scene_key, cur_lines, prepend, event, forbidden_lines, (next_remark_string, lines_since_remark))
            if pregenerate:
                self.pregenerate_queue.put(queue_item)
            else:
                self.generate_queue.put(queue_item)

            # synchronous wait
            event.wait()
            assert cur_scene_key in self.results, cur_scene_key
            # wait for the values to be filled
            while not self.results[cur_scene_key]:
                time.sleep(1)
            return self.results[cur_scene_key]

    # To define forbidden lines.
    # Only works if cur_scene_key does not end with a command.
    def get_previous_line_values(self, cur_scene_key):
        # We forbid lines that the user rejected (by clicking the red
        # cross), so e.g. when generating a line with id 'd', we
        # forbid the previously generated variants 'a', 'b' and 'c'.
        prefix = cur_scene_key[:-1]
        cont_part = cur_scene_key[-1]
        forbidden_lines = []
        if cont_part in string.ascii_lowercase and cont_part != 'a':
            self.lock.acquire()
            # for characters from 'a' to the requested cont_part (exclusively)
            for prev_cont_part_ord in range(ord('a'), ord(cont_part)):
                prev_key = prefix + chr(prev_cont_part_ord)
                db_line = self.db['lines'].find_one(key=prev_key)
                if db_line:  # it's not 100% guaranteed the variant exists (e.g. manual URL entry)
                    forbidden_lines.append(db_line['text'].strip())
            self.lock.release()
        return forbidden_lines

    # Get line for the key; return None if missing; generate translation if translation missing
    def get_line_from_db(self, scene_key):
        self.lock.acquire()
        db_line = self.db['lines'].find_one(key=scene_key)
        self.lock.release()
        if db_line is not None and self.translate and not db_line.get('cs_text'):
            db_line['cs_text'] = urutranslate.translate_with_roles_separately(db_line['text'])
            self.lock.acquire()
            self.db['lines'].update(db_line, ['id', 'key'])
            self.lock.release()
        return db_line


    # Get prompt and outline for the key; throw exception if missing; generate translation if translation missing
    def get_prompt_and_outline_from_db(self, prompt_key):

        # Get the prompt (and outline)
        self.lock.acquire()
        prompt = self.db['scenes'].find_one(key=prompt_key)
        self.lock.release()
        if not prompt:
            raise Exception('Scene not found!')

        # Fill in missing translations
        if self.translate:
            update = False
            if not prompt.get('cs_prompt'):
                prompt['cs_prompt'] = urutranslate.translate_with_roles_separately(prompt['prompt'])
                update = True
            if prompt['outline'] and not prompt.get('cs_outline'):
                prompt['cs_outline'] = urutranslate.translate_with_roles_separately(prompt['outline'])
                update = True
            if update:
                self.lock.acquire()
                self.db['scenes'].update(prompt, ['id', 'key'])
                self.lock.release()

        return prompt

    def get_text(self, scene_key, pregenerate=False, username=''):
        """Getting scene text (from DB or generating new)."""
        pre = 'pre' if pregenerate else ''
        logger.info(f'SERVER: {pre}getting text {compress_key(scene_key)}...')

        key = split_into_parts(scene_key)
        prompt_key = key[0]
        cont_key = key[1:]

        # Get the scene prompt and outline
        db_line = self.get_prompt_and_outline_from_db(prompt_key)
        prompt = db_line['prompt']
        cs_prompt = db_line.get('cs_prompt')
        outline_text = db_line['outline']
        cs_outline = db_line.get('cs_outline')
        char1 = db_line.get('char1')
        char2 = db_line.get('char2')

        # Find the continuing lines
        # current scene key
        cur_scene_key = prompt_key + '-'
        # list of current lines, eventually pertaining to the scene_key
        # a line may be empty if it is cut
        lines = []
        # for each line, its translation
        cs_lines = []
        # for each line, its forbidden lines in case we want to regenerate it
        forbidden_lines = []

        for cont_part in cont_key:
            cur_scene_key += cont_part
            if len(cont_part) == 1:
                # standard insertion
                command = None
                # generate at the end
                position = len(lines)
            else:
                # cut, addition, or regeneration
                command = cont_part[-1]
                assert command in {CUT, ADD, REG}, cont_part
                # generate at specified position
                position = int(cont_part[:-1])

            if command == CUT:
                # Cut according to the command
                # Now the line is forbidden at that position
                forbidden_lines[position].append(lines[position])
                # Now the line is empty
                lines[position] = ''
                cs_lines[position] = ''
                # And no need to generate or do anything more
            else:
                # Set/update forbidden lines, prepare position for the line
                if command == ADD:
                    # Insert before set position
                    forbidden_lines.insert(position, [])
                    if position > 0 and lines[position-1] == '':
                        # If previous line was cut, its forbidden lines are also forbidden for this line
                        forbidden_lines[position].extend(forbidden_lines[position-1])
                    lines.insert(position, None)
                    cs_lines.insert(position, None)
                elif command == REG:
                    # The position already exists
                    # Current value of the line is forbidden
                    forbidden_lines[position].append(lines[position])
                    lines[position] = None
                    cs_lines[position] = None
                else:
                    # Standard generating: add at end
                    # previous variants of the line are forbidden
                    forbidden_lines.append(self.get_previous_line_values(cur_scene_key))
                    lines.append(None)
                    cs_lines.append(None)

                # Look for the line in DB
                db_line = self.get_line_from_db(cur_scene_key)
                # Put the line at prepared position
                if db_line:
                    # Found in DB -- no need to generate
                    lines[position] = db_line['text']
                    cs_lines[position] = db_line.get('cs_text')
                else:
                    # Not found -- need to generate
                    input_lines, prepend_char = self.join_prompt_and_lines(prompt, lines[:position], char1, char2)
                    lines[position], cs_lines[position] = self.generate_line(
                            cur_scene_key,
                            input_lines,
                            forbidden_lines[position],
                            outline_text,
                            pregenerate,
                            prepend_char)

        if not pregenerate:

            # store access log
            log_data = {'key': scene_key,
                        'username': username,
                        'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

            self.lock.acquire()
            # keep previous rating, if by the same user
            rating = self.db['access_log'].find(key=scene_key, order_by=['-timestamp'])
            rating = next(iter([r for r in rating if r.get('rating')]), None)
            if rating is not None and rating['username'] == username:
                log_data['rating'] = rating['rating']
            # insert into DB
            self.db['access_log'].upsert(log_data, ['key', 'username'])
            self.lock.release()
            # return the result
            rating = rating['rating'] if rating is not None else None
            value = {'key': scene_key, 'prompt': prompt, 'lines': lines, 'outline': outline_text, 'rating': rating}
            if self.translate:
                value['cs_prompt'] = cs_prompt
                value['cs_lines'] = cs_lines
                value['cs_outline'] = cs_outline
            return value

    # event: a threading.Event on which a thread is waiting for the result
    def store_result(self, scene_key, result, prepend='', event=None):
        assert 'lines' in result
        logger.info('SERVER: storing {} lines starting at {}'.format(
                    len(result['lines']), compress_key(scene_key)))
        # Managing the results
        lines = result['lines']
        cs_lines = []
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if lines and prepend:
            lines[0] = prepend + lines[0]

        for line in lines:
            db_line = {'key': f"{scene_key}",
                       'text': line,
                       'model': result['model'],
                       'server_version': self.server_version,
                       'git_version': self.git_version,
                       'git_branch': self.git_branch,
                       'timestamp': ts}
            cs_text = ''
            if self.translate:
                cs_text = urutranslate.translate_with_roles_separately(line)
                db_line['cs_text'] = cs_text
                cs_lines.append(cs_text)

            logger.info('SERVER: storing line {}: {}'.format(
                compress_key(scene_key), repr(line)))
            self.lock.acquire()
            self.db['lines'].insert_ignore(db_line, ['key'])
            self.lock.release()
            self.results[scene_key] = line, cs_text

            scene_key += 'a'

        # if a thread is waiting, notify the thread
        if event:
            event.set()

        return

    def store_empty_line(self, scene_key):
        return self.store_result(scene_key, {'lines': [''], 'model': '(empty)'})

    def list_scenes(self, username_limit=None, outline_limit=None):
        """Getting a listing of all scenes.
        If username_limit contains a user name string, only scenes created by
        that user are listed.
        If outline_limit evaluates to True, only scenes that also have an
        outline (synopsis) specified are listed."""
        logger.info(f'SERVER: listing scenes...')
        res = {}
        self.lock.acquire()
        if username_limit and outline_limit:
            # The specified user AND non-empty outline
            scenes = self.db['scenes'].find(username=username_limit, outline={'not': ''})
        elif username_limit:
            # The specified user
            scenes = self.db['scenes'].find(username=username_limit)
        elif outline_limit:
            # Non-empty outline
            scenes = self.db['scenes'].find(outline={'not': ''})
        else:
            # All scenes
            scenes = self.db['scenes']
        self.lock.release()
        for scene in scenes:
            res[scene['key']] = {'prompt': scene['prompt'], 'cs_prompt': scene['cs_prompt'], 'username': scene.get('username')}
        res = {'scenes': res}
        if username_limit:
            res['username'] = username_limit
        return res

    def list_recent_keys(self, page_len, page_no, username_limit=None):
        """List recently generated keys."""
        self.lock.acquire()
        if username_limit:
            acc_keys = self.db['access_log'].find(username=username_limit, order_by='-timestamp')
        else:
            acc_keys = self.db['access_log'].find(order_by='-timestamp')
        self.lock.release()
        acc_keys = list(acc_keys)
        if page_len:
            acc_keys = acc_keys[page_no * page_len:]
            acc_keys = acc_keys[:page_len]
        res = []
        for acc_key in acc_keys:
            res.append(dict(acc_key))
        res = {'recent': res}
        if username_limit:
            res['username'] = username_limit
        return res

    def search_db(self, field, query):
        assert (field in ['prompt', 'cs_prompt', 'text', 'cs_text'])
        table = 'scenes' if field in ['prompt', 'cs_prompt'] else 'lines'
        self.lock.acquire()
        res = self.db.query(f"SELECT * FROM {table} WHERE {field} LIKE :query_str", query_str='%' + query + '%')
        self.lock.release()
        res = {'results': [dict(r) for r in res], 'search': field, 'query': query}
        return res

    def store_rating(self, key, rating, username):
        data = {'key': key,
                'username': username,
                'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'rating': rating}
        self.lock.acquire()
        self.db['access_log'].upsert(data, ['key', 'username'])
        self.lock.release()
        return data

    def shutdown(self):
        """Shutdown the underlying Flask server. Needs to get into internals."""
        self.queue_thread_should_run = False
        self.queue_thread.join()
        if not self.as_console:
            shutdown_hook = flask.request.environ.get('werkzeug.server.shutdown')
            shutdown_hook()

    def process_command(self, data):
        """Handling of JSON input commands (used both by Flask server and command line)."""
        if 'ping' in data:
            return 'ping'
        if data.get('killme') == 'now':
            self.shutdown()
            return 'bye'
        # store a new scene in the DB
        if 'scene' in data:
            return self.store_new_scene(data['key'], data['scene'], data.get('username', ''),
                    data.get('outline'), data.get('char1'), data.get('char2'))

        # server internally works with expanded line keys only (scene names are not affected)
        for k in ['key', 'pregenerate']:
            if k in data:
                if not validate_key(data[k]):
                    raise Exception(f"Invalid key: {data[k]}")
                data[k] = expand_key(data[k])

        if 'human_input' in data:
            return self.store_human_input(data['key'], data['human_input'], data.get('input_type', 'human'))
        elif 'rating' in data:
            return self.store_rating(data['key'], data['rating'], username=data.get('username', ''))
        elif 'key' in data:
            # get/generate scene continuation
            return self.get_text(data['key'], username=data.get('username', ''))
        elif 'search' in data:
            return self.search_db(data['search'], data['query'])
        elif 'pregenerate' in data:
            # pregenerate scene continuation
            x = threading.Thread(target=self.get_text,
                                 args=(data['pregenerate'], True))
            x.start()
            return ''
        elif 'recent' in data:
            return self.list_recent_keys(data['recent'], data.get('page', 0), data.get('username_limit'))
        elif 'list_scenes' in data:
            return self.list_scenes(data.get('username_limit'), data.get('outline_limit'))
        assert False, "Incorrect command: " + str(data)

    def handle_console_requests(self):
        """Main console method -- process JSON on stdin, one-per-line, output to stdout."""
        while True:
            data = sys.stdin.readline()
            if not data:
                break
            try:
                result = self.process_command(json.loads(data.strip()))
                print(json.dumps(result), flush=True)
            except Exception as e:
                logger.exception(str(e))
                print()
        logger.info('END OF COMMANDS')

    def handle_server_request(self):
        """Main method to use for Flask requests."""
        # get parameters
        data = flask.request.json
        try:
            result = self.process_command(data)
            return flask.jsonify(result)

        except Exception as e:
            logger.exception(str(e))
            return str(e), 500


if __name__ == '__main__':
    torch.multiprocessing.set_start_method('spawn')
    ap = ArgumentParser(description='Story generation backend server')
    ap.add_argument('-C', '--console', action='store_true',
                    help='Process JSON from standard input, then terminate.')
    ap.add_argument('-p', '--port', default=8456,
                    help='Port on which this server runs')
    ap.add_argument('-H', '--host', default='127.0.0.1',
                    help='Host/interface on which this server runs (defaults to localhost)')
    ap.add_argument('-n', '--num-alternatives', default=5,
                    help='Number of alternative lines to generate')
    ap.add_argument('-m', '--model', default='distilgpt2',
                    help='HuggingFace model to be used')
    ap.add_argument('-d', '--database', default='database.db',
                    help='Database file to be used')
    ap.add_argument('-t', '--translate', action='store_true',
                    help='Translate outputs to Czech on display?')
    ap.add_argument('-s', '--summarize', default=True,
                    help="Whether to summarize instead of just clipping prompt")
    ap.add_argument('-r', '--no-ban-remarks', default=True, dest='ban_remarks', action='store_false',
                    help="Do not ban remarks")
    ap.add_argument('-P', '--prose', default=False, action='store_true',
                    help="Is the text generated by this instance prose (summaries) or drama?")
    ap.add_argument('-N', '--nli', default=False, action='store_true',
                    help="Should NLI filtering be used?")
    ap.add_argument('-o', '--outlines', action='store_true',
                    help="Auto insert lines from outline?")
    ap.add_argument('-l', '--log-level', choices=['debug', 'info', 'warning', 'error'], default='debug',
                    help='Logging error level')
    args = ap.parse_args()

    # set global logging level (the getattr thing just converts 'debug' to logging.DEBUG etc.)
    log_level = getattr(logging, args.log_level.upper())
    loglevel(log_level)

    server_conn, gen_conn = multiprocessing.Pipe()
    # start the child generator process (pass over the logging level)
    generator = Generator(gen_conn, args.model, args.num_alternatives, summarize=args.summarize, log_level=log_level,
            ban_remarks=args.ban_remarks, prose=args.prose, use_nli=args.nli)
    generator.start()
    # parent process: start Flask server
    server = Server(server_conn, args.database, args.num_alternatives,
            args.translate, as_console=args.console, outlines=args.outlines)
    if args.console:
        server.handle_console_requests()
        server.shutdown()
    else:
        app = flask.Flask(__name__)
        app.add_url_rule('/', 'handle_server_request', server.handle_server_request, methods=['POST'])
        app.run(host=args.host, port=args.port, threaded=True)
    logger.warning('Main server thread (and queue thread) stopped. Killing generator...')
    server_conn.close()
    generator.terminate()
    generator.join()
    logger.warning('SERVER: Generator terminated')
