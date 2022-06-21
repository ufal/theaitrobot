#!/usr/bin/env python3
#coding: utf-8

import requests
import sys
from functools import lru_cache

import logging
logging.basicConfig(
    format='%(asctime)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.ERROR)

_headers = {"accept": "text/plain"}

# from story_server import looks_scenic
def looks_scenic(line):
    """Does this line look like a scenic remark?"""
    return (line.strip().startswith('[') or ':' not in line)

def _trim(text):
    text = text.replace('\n', '  ')
    if len(text) > 20:
        return '{}...'.format(text[:17])
    else:
        return text

@lru_cache(maxsize=4)
def get_url(source='en', target='cs'):
    return f'http://lindat.mff.cuni.cz/services/translation/api/v2/models/{source}-{target}'

@lru_cache(maxsize=32)
def translate(text, source='en', target='cs'):
    """Simply translate the text"""

    if text.strip() == '':
        # translating empty text is trivial
        return text

    data = {"input_text": text}
    
    logging.debug('Sending request: {} characters ({})'.format(
        len(text), _trim(text)))
    response = requests.post(
            get_url(source, target),
            data = data,
            headers = _headers)
    logging.debug('Got response: {} {}'.format(
        response.status_code, response.reason))
    response.encoding='utf8'
    
    if response.status_code == 200:
        translation = response.text
        # Transformer eats up empty lines at the beginning
        if text.startswith('\n'):
            assert not translation.startswith('\n'), "Ah they fixed Transformer so it does not eat up initial empty lines anymore!"
            prepend = ''
            position = 0
            while text[position] == '\n' and position < len(text):
                prepend += '\n'
                position += 1
            translation = prepend + translation
        # At the end we also have to be careful
        # Transformer adds an empty line at the end so let's first remove that
        translation = translation.rstrip() 
        # And now let's add empty lines if necessary
        if text.endswith('\n'):
            append = ''
            position = len(text) - 1
            while text[position] == '\n' and position >= 0:
                append += '\n'
                position -= 1
            translation = translation + append
        logging.info('Got translation: {} characters ({})'.format(
            len(translation), _trim(translation)))
        return translation
    else:
        logging.error('Translation error: {} {}'.format(
            response.status_code, response.reason))
        return None

@lru_cache(maxsize=8)
def translate_role(role, source='en', target='cs'):
    """Translate character name"""

    # It seems roles are best translated in titlecase...
    # (to favour interpretation as character name/role)
    text_to_translate = role.title()

    if source == 'en':
        # ...preceded with 'the'
        # (to favour base form)
        if not text_to_translate.lower().startswith('the '):
            text_to_translate = 'the ' + text_to_translate

    translation = translate(text_to_translate, source, target)

    if role.istitle():
        translation = translation.title()
    elif role.isupper():
        translation = translation.upper()
    elif role.islower():
        translation = translation.lower()

    return translation

def translate_scenic(text, source='en', target='cs'):
    """Translate scenic remark"""

    text_to_translate = text
    prepend = ''
    append = ''

    # If remark in square brackets, remove the brackets for translation.
    # TODO: Might also be other brackets etc.
    if text_to_translate.startswith('[') and text_to_translate.endswith(']'):
        text_to_translate = text[1:-1].strip()
        prepend = '['
        append = ']'

    translation = translate(text_to_translate, source, target)

    # Put back what was removed
    translation = prepend + translation + append

    return translation


def translate_with_roles_separately(text, source='en', target='cs'):
    """Split up the lines into character names and character lines and
    translate these separately"""

    lines_original = text.split('\n')
    lines_translation = []
    for line_full in lines_original:
        if looks_scenic(line_full):
            logging.debug('Translating scenic line: "{}"'.format(line_full))
            translation_full = translate_scenic(line_full, source, target)
            lines_translation.append(translation_full)
        else:
            character, line = line_full.split(':', 1)
            logging.debug('Splitting line for translation: "{}" : "{}"'.format(
                character, line.lstrip()))
            character_translation = translate_role(character, source, target)
            line_translation = translate(line.lstrip(), source, target)
            translation_full = '{}: {}'.format(
                    character_translation, line_translation)
            lines_translation.append(translation_full)

    return '\n'.join(lines_translation)

if __name__=="__main__":
    import sys
    from argparse import ArgumentParser
    ap = ArgumentParser(description='Translation service, translates text from STDIN to STDOUT')
    ap.add_argument('-s', '--source', default='en',
            help='Source language; default: en')
    ap.add_argument('-t', '--target', default='cs',
            help='Target language; default: cs')
    args = ap.parse_args()
    
    for line in sys.stdin:
        print(translate(line.rstrip(), source=args.source, target=args.target))

    # OR for theatre script with character names and scenic remarks...
    # print(translate_with_roles_separately(line.rstrip()))

    # OR read input from file
    # with open(sys.argv[1]) as infile:
    #     for line in infile...
