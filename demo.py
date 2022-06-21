#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import cgi
import html
import http
import requests
import traceback
import json
import string
import subprocess

import i18n
i18n.set('filename_format', '{locale}.{format}')
i18n.load_path.append('i18')

from keyops import compress_key, expand_key
from cgi_common import load_config

import logging
logging.basicConfig(
    format='%(asctime)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.WARN)

DOWN = False

username_display = 'demo_inputs'
username_insert = 'demo_user'

SERVER_ADDR, _ = load_config('config.json')
SERVER_ADDR_SYN, _ = load_config('syn_config.json')

EOT = '<|endoftext|>'

REGENERATE_FOR_EACH_LINE = True

# get parameters
def cgi_to_dict(field_storage):
    """ Get a plain dictionary rather than the '.value' system used by the
    cgi module's native field_storage class. """
    params = {}
    for key in field_storage.keys():
        if isinstance(field_storage[key], list):
            params[key] = field_storage[key][0].value
        else:
            params[key] = field_storage[key].value
    return params

args = cgi_to_dict(cgi.FieldStorage())

# set PAGE
PAGE = 'intro'
if 'page' in args and args['page'] in ('intro', 'welcome1', 'welcome2', 'script', 'syn', 'syn2script'):
    PAGE = args['page']

# set LANGUAGE
if 'language' in args and args['language'] == 'cs':
    LANGUAGE = 'cs'
    L_ = 'cs_'
else:
    LANGUAGE = 'en'
    L_ = ''
i18n.set('locale', LANGUAGE)

KEY = args.get('key')

def nl2br(s):
    return '<br />\n'.join(s.split('\n'))

def link(page=PAGE, language=LANGUAGE, key=''):
    if KEY and not key:
        key = KEY
    return f'''?page={page}&amp;language={language}&amp;key={compress_key(key)}'''

def get_backlink(key):
    """Add link to previous chosen option from this point."""
    key = expand_key(key)
    prefix = key[:-1]
    current = key[-1]
    if current in ('a', 'A'):
        # at first variant: go back one step
        return link(key=prefix)
    else:
        # at later variant: go to previous variant
        new = chr(ord(current) - 1)
        if new in string.ascii_letters:
            return link(key=prefix + new)
        else:
            # assert False
            logging.warning(f'Cannot get_backlink for "{key}"')
            return None

def get_newkey(key):
    key = expand_key(key)
    prefix = key[:-1]
    current = key[-1]
    new = chr(ord(current) + 1)
    if new in string.ascii_lowercase:
        return prefix + new
    else:
        return None

def print_header(page=PAGE):

    backline = ''
    if KEY:
        backlink = get_backlink(KEY)
        if backlink:
            backline = f'''<a class='right' href="{backlink}" title="{i18n.t('O krok zpět')}"><img class='logo-image' src="static/arrow_left_white.png" alt="←"></a>'''

    if PAGE != 'intro':
        otherlang = 'cs' if LANGUAGE == 'en' else 'en'
        switch_language = f'''<a class='left' href='{link(language=otherlang)}'>{i18n.t('Switch to English')}</a>'''
    else:
        switch_language = ''

    title_tool = 'THEaiTRobot'
    if PAGE in ('welcome1', 'script'):
        title_tool += ' 1.0'
    if PAGE in ('welcome2', 'syn', 'syn2script'):
        title_tool += ' 2.0'

    title_type = ''
    if PAGE in ('script', 'syn2script'):
        title_type = i18n.t('Scénář')
    elif PAGE == 'syn':
        title_type = i18n.t('Synopse')

    title_key = compress_key(KEY) if KEY else ''

    title_separator = ''
    if title_type or title_key:
        title_separator = '|'

    print(f'''Content-Type: text/html; charset=UTF-8

<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="utf-8">
    <title>{title_tool} {title_separator} {title_type} {title_key}</title>
    <meta name="description" content="THEaiTRobot demo">
    <link rel="stylesheet" href="static/index.css">
    <script defer src="static/script.js"></script>
</head>

<body id="body_{page}" data-thisurl="{link()}">

    <div class='navbar'>
        <a class='left' href='https://theaitre.com/' title="{i18n.t('Projekt THEaiTRE')}"><img class='logo-image' src="static/theaitre_logo.png" alt="THEaiTRE"></a>
        <a class='left {'selected' if PAGE in ('welcome1', 'script') else ''}' href='{link('welcome1', key='')}'>THEaiTRobot 1.0</a>
        <a class='left {'selected' if PAGE in ('welcome2', 'syn', 'syn2script') else ''}' href='{link('welcome2', key='')}'>THEaiTRobot 2.0</a>
        {switch_language}
        <a class='right' href="{link('intro', key='')}" title="{i18n.t('Hlavní stránka')}"><img class='logo-image' src="static/home_button.png" alt="🏠"></a>
        {backline}
    </div>

    <div class="onlyprint">
        <h1><img src="static/theaitre_logo.png" alt="THEaiTRE"></h1>
        <h2>{title_tool}</h2>
        <h3>{title_type} {title_key}</h3>
    </div>

    <div id="processing_block">
        <div class="processing_align">
            <div>
                <img src="robot.gif" alt="Robot">
            </div>

            <div class="text">
                <h1 id="title-switcher" data-value="0" class="processing_text">{i18n.t('Zpracovává se')}</h1>
            </div>
        </div>
    </div>

    <div id="main">
''')

def print_generate_header():
    pass

# TODO maybe this could be done better but maybe this good enough?
# TODO assumes we use entire lines, not e.g. cut into smaller pieces. This
# shall be ensured when creating the synopsis; it should be split into
# sentences so that there is no need to further split it into smaller chunks.
def find_first_unused_outline_line(lines, outline, cs_outline):
    """Find first outline line that has not been used yet."""
    used = set( (line.strip() for line in lines) )

    for line, cs_line in zip(outline.split('\n'), cs_outline.split('\n')) :
        line = line.strip()
        if f'[{line}]' not in used:
            return {'line': line, 'cs_line': cs_line}

    return None

def extract_characters(lines, cs_lines):
    """Get all character names.

    Order from most recent to least recent,
    always add Man and Woman to have something, switch first two.
    Gets all character names already used in the generated script.
    Also returns number_of_characters: number if lines already contain
    some lines said by some character ("Character: line"), 0 otherwise
    i.e. lines is empty or only contains scenic remarks etc.
    TODO:
    - Probably also try to extract character names from the synopsis using
    NER or something like that.
    - Probably also from prompt?
    """

    # All characters that appear in lines,
    # going in reverse order to have most recent characters first
    # (ordered because dicts are ordered in Python)
    characters = dict()
    for line, cs_line in zip(reversed(lines), reversed(cs_lines)):
        line = line.strip()
        colon_position = line.find(':')
        if colon_position != -1:
            # Character name excluding colon
            character = line[:colon_position]
            character_cs = cs_line.strip().split(':')[0]
            if character not in characters:
                characters[character] = {
                        'name': character,
                        'cs_name': character_cs,
                        'count': 1}
            else:
                characters[character]['count'] += 1
    number_of_characters = len(characters)

    # Always have these two
    for default_character in (
            { 'name': 'Man', 'cs_name': 'Muž', 'count': 1},
            { 'name': 'Woman', 'cs_name': 'Žena', 'count': 1}):
        if default_character['name'] not in characters:
            characters[default_character['name']] = default_character

    # Switch first two; it is most likely that the penultimate character
    # will speak now, not the one that has just spoken.
    # We are guaranteed to have at least two characters because of the two defaults.
    characters_list = list(characters.values())
    characters_list[0], characters_list[1] = characters_list[1], characters_list[0]

    return characters_list, number_of_characters


def print_controls(data, is_eot, is_partial=False):
    """Print generation controls"""

    if PAGE in ('script', 'syn'):
        print(f'''<div class="mom"><div class='titulek'></div><div class='okenko_blank'>''')

        # for syn, allow to generate script from synopsis only if is_eot or has at least 5 lines
        if PAGE == 'syn' and (is_eot or len(data[L_+'lines']) >= 5):
            print(f'''<a href="{link(page='syn2script')}&amp;add=1" class="generovat" title="{i18n.t('Ukončit generování synopse a přejít ke generování scénáře z této synopse')}">
                    {i18n.t('GENEROVAT SCÉNÁŘ Z TÉTO SYNOPSE')}
                </a>''')
        else:
            print('''<div></div>''')

        # allow generating a new line unless end of text
        if not is_eot:
            print(f'''<a href="{link(key=data['key'] + 'a')}" class="add_tlacitko" title="{i18n.t('Generovat dál')}"></a>''')
            print(f'''<a href="{link(key=data['key'] + 'aaaaa')}" class="add_tlacitko" title="{i18n.t('Generovat dál')} (5x)">5</a>''')
            print(f'''<a href="{link(key=data['key'] + 'aaaaaaaaaa')}" class="add_tlacitko" title="{i18n.t('Generovat dál')} (10x)">10</a>''')
        else:
            print('''<div></div>''')

        print(f'''</div></div>''')
        print('</div>')
    else:
        assert PAGE == 'syn2script'
        print('</div> <div id="syn2script_controls">')

        if is_eot:
            # Early exit, nothing more to generate
            return

        print(f'''<h3>{i18n.t('ZVOLTE, JAK POKRAČOVAT V GENEROVÁNÍ')}</h3>''')

        # We always want to insert the English synopsis line/character name
        # TODO except for manually written character name: TODO translate it
        # Thus each synopsis line as well as each character is actually a dict
        # contatining a pair of items, under the keys 'line', 'cs_line'
        # or 'name', 'cs_name'
        syn_line = find_first_unused_outline_line(
                data['lines'], data['outline'], data['cs_outline'])
        # There are always two default characters (Man and Woman) who do not
        # count towards number_of_characters
        characters, number_of_characters = extract_characters(
                data['lines'], data['cs_lines'])

        if number_of_characters >= 2 or is_partial:
            # Simply generate a line ('a')
            # If there are at least two characters already, we can trust the
            # model to probably generate something reasonable
            print(f'''<div class='controls'>
                <div class='next'>
                    <a href="{link(key=data['key'] + 'a')}" class="add_tlacitko" title="{i18n.t('Generovat další repliku dle modelu')}"></a>
                    <h4>{i18n.t('další řádek')}</h4>
                </div>
            </div>''')

        if syn_line and not is_partial:
            # Insert line from synopsis
            print(f'''<form class='controls' method="post" action="{link()}">
                <div class='next'>
                    <div class="okenko_syn_running">
                        <p>{html.escape(syn_line[L_+'line'])}</p>
                        <input type="hidden" name="human_input" value="{html.escape(syn_line['line'])}">
                        <input type="hidden" name="input_type" value="syn_line">
                    </div>
                </div>
                <div class='next'>
                    <input type="submit" value="" class="add_tlacitko" title="{i18n.t('Vložit další větu z vygenerované synopse')}">
                    <h4>{i18n.t('synopse')}</h4>
                </div>
            </form>''')

        if data['lines'] and not is_partial:
            # Insert existing character name and generate a line
            print(f'''<div class='controls'>''')
            for char_name in characters:
                print(f'''<form class='next' method="post" action="{link()}">
                        <input type="hidden" name="human_input" value="{html.escape(char_name['name'])}">
                        <input type="hidden" name="input_type" value="char_name">
                        <input type="submit" value="" class="add_tlacitko" title="{i18n.t('Generovat repliku postavy')} {html.escape(char_name[L_+'name'])}">
                        <h4>{html.escape(char_name[L_+'name'])}</h4>
                    </form>''')
            print(f'''</div>''')

            # Insert new character name and generate a line
            print(f'''<form class="controls" method="post" action="{link()}">
                    <input class="add_tlacitko" type="submit" title="{i18n.t('Generovat repliku zadané nové postavy')}" value="">
                    <input type="hidden" name="input_type" value="char_name">
                    <textarea class="textarea_char" name="human_input" placeholder="{i18n.t('Jméno nové postavy')}"></textarea>
            </form>''')

        print('</div>')


def print_generate_footer(key, sent_email):

    if sent_email:  # just a message that email has been sent
        print(f'''
    <div id="email_block">{i18n.t('Odesláno!')}</div>
''')
        return

    # TODO retest emails

    # TODO add download

    # no email sent: email address entry form
    print(f'''
    </div>

    <form action="{link(key=key)}" method="post">
        <div id="email_block">

            <input class="email_form" name="email_address" placeholder="your@email.cz">
            <button class="email_tlacitko" name="send_mail" value="send_mail" type="submit">
                <img class="icon" src="static/email.png" alt="e-mail">
            </button>

        <!--<form>
            <button class="email_tlacitko" id='test' type="button">
                <img class="icon" src="static/download.png" alt="download">
            </button>
        </form>-->

        </div>
    </form>
''')

def print_intro():
    print(f'''
        <h2>{i18n.t('MŮŽE ROBOT VYMYSLET DIVADELNÍ HRU?')}</h2>

        <div class='main_controls'>
            <div>
                {i18n.t('theaitrobot10intro')}
                <a href="{link('welcome1', language=LANGUAGE)}" class="generovat">{i18n.t('VYZKOUŠET')}</a>
            </div>
            <div>
                {i18n.t('theaitrobot20intro')}
                <a href="{link('welcome2', language=LANGUAGE)}" class="generovat">{i18n.t('VYZKOUŠET')}</a>
            </div>
        </div>
''')

def print_index_header():
    title = i18n.t('UKÁZKOVÝ SCENÁŘ') if PAGE == 'welcome1' else i18n.t('UKÁZKOVÝ NÁZEV')
    print(f'''
        <h2>{i18n.t('MŮŽE ROBOT VYMYSLET DIVADELNÍ HRU?')}</h2>

        <div class="nazev-bloku">
            <h3>{title}</h3>
        </div>
''')

def print_index_block(lines, my_key, prev_key, next_key, hide):
    style = 'style="display: none"' if hide else ''

    if PAGE == 'welcome1':
        nextpage = 'script'
        buttontext = i18n.t('GENEROVAT DÁL')
        prevname = i18n.t('Předchozí ukázkový scénář')
        nextname = i18n.t('Další ukázkový scénář')
        genwhat = i18n.t('Vygenerovat pokračování scénáře')
    else:
        assert PAGE == 'welcome2'
        nextpage = 'syn'
        buttontext = i18n.t('GENEROVAT SYNOPSI')
        prevname = i18n.t('Předchozí ukázkový název')
        nextname = i18n.t('Další ukázkový název')
        genwhat = i18n.t('Vygenerovat synopsi hry')

    print(f'''
        <div class="first_block" id="scriptblock_{my_key}" {style}>
            <div class="shift">
''')

    for line in lines.split('\n'):
        if line.strip():
            print_line(line, prompt=True)

    print(f'''
                <div class="buttons">
                    <div class="sipkal" onclick='show_hide("scriptblock_{prev_key}", "scriptblock_{my_key}")' title="{prevname}"></div>
                    <div class="sipkar" onclick='show_hide("scriptblock_{next_key}", "scriptblock_{my_key}")' title="{nextname}"></div>

                    <a class="generovat" href="{link(page=nextpage, key=my_key+'-a')}" title="{genwhat}">
                        {buttontext}
                    </a>

                </div>

            </div>
        </div>
''')

# TODO form: check if something is filled in
def print_insert_form():
    if PAGE == 'welcome1':
        print(f'''
            <div class="nazev-bloku" style="margin-top:60px;">
                <h3>{i18n.t('ZADEJTE VLASTNÍ SCENÁŘ')}</h3>
                <p>{i18n.t('AI vygeneruje pokračování')}</p>
            </div>

            <div class="first_block">
                <div class="shift">
                    <form method="post" action="{link('script')}">
                        <input type="hidden" name="add" value="1">
                        <div class='mom'>

                            <div class="titulek ital">
                                <p>{i18n.t('Scéna')}</p>
                            </div>


                            <div>
                                <textarea  class="textarea_big" placeholder="{i18n.t('Sem napište popis výchozí situace.')}" name="prompt"></textarea>
                            </div>

                        </div>

                        <div class='mom'>

                            <div class="titulek">
                                <textarea class="textarea_char" placeholder="{i18n.t('Jméno první postavy')}" name="char1"></textarea>
                            </div>


                            <div>
                                <textarea  class="textarea_big" placeholder="{i18n.t('Sem napište, co řekne první postava.')}" name="line1"></textarea>
                            </div>

                        </div>

                        <div class='mom'>

                            <div class="titulek">
                                <textarea class="textarea_char" placeholder="{i18n.t('Jméno druhé postavy')}" name="char2"></textarea>
                            </div>


                            <div>
                                <textarea  class="textarea_big" placeholder="{i18n.t('Sem napište, co řekne druhá postava.')}" name="line2"></textarea>
                            </div>

                        </div>


                        <div class="buttons">
                            <button class="generovat" type="submit" title="{i18n.t('Vygenerovat pokračování scénáře')}">
                                {i18n.t('GENEROVAT DÁL')}
                            </button>
                        </div>
                    </form>
                </div>''')
    else:
        assert PAGE == 'welcome2'
        print(f'''
            <div class="nazev-bloku" style="margin-top:60px;">
                <h3>{i18n.t('ZADEJTE VLASTNÍ NÁZEV HRY')}</h3>
                <p>{i18n.t('AI vygeneruje synopsi')}</p>
            </div>

            <div class="first_block">
                <div class="shift">
                    <form method="post" action="{link('syn')}">
                        <input type="hidden" name="add" value="1">
                        <div class='mom'>

                            <div class="titulek ital">
                                <p>{i18n.t('Název hry')}</p>
                            </div>


                            <div>
                                <input class="textarea_big" placeholder="{i18n.t('Sem napište název hry.')}" name="prompt">
                            </div>

                        </div>

                        <div class="buttons">
                            <button class="generovat" type="submit" title="{i18n.t('Vygenerovat synopsi hry')}"> {i18n.t('GENEROVAT SYNOPSI')}</button>
                        </div>
                    </form>
                </div>''')

def print_about_project():
    print(f'''
                <div class="robotik">
                    <img src="static/sipka_dolu.png" style="height: 50px;" alt="↓">
                    <img src="static/robot.png" alt="robot">
                </div>

            </div>
        </div>

    <div id="theaitre" class="credits_block">
        {i18n.t('oprojektu')}
    </div>''')

def print_logos():
    print(f'''
    <div id="main_2">
            <div class="row">
                <a href="https://www.matfyz.cz/">
                    <img class="obrazek" src="static/mff.png" alt="MFF logo">
                </a>
                <a href="https://www.tacr.cz/">
                    <img class="obrazek" src="static/tacr.png" alt="TACR logo">
                </a>
                <a href="https://www.tacr.cz/program/program-eta/">
                    <img class="obrazek" src="static/eta.png" alt="ETA logo">
                </a>
            </div>

            <p><br>{i18n.t('Projekt je spolufinancován se státní podporou Technologické agentury ČR v rámci Programu ÉTA 3.')}<br></p>

            <div class="row">
                <a href="https://ufal.mff.cuni.cz/">
                  <img class="obrazek" src="static/ufal.png" alt="UFAL logo">
                </a>
                <a href="https://www.svandovodivadlo.cz/">
                  <img class="obrazek" src="static/svandovo.png" style="width: 150px;" alt="Svandovo divadlo logo">
                </a>
                <a href="https://www.damu.cz/">
                  <img class="obrazek" src="static/damu.png" alt="DAMU logo">
                </a>
            </div>
    </div>
''')

def print_footer():
    print('''
    <h3 class="onlyprint">www.theaitre.com</h3>
</body>
</html>
''')


def print_line(line, newkey=None, prompt=False):
    is_partial = False

    # regenerate button
    if newkey:
        newkeyline = f'''<a href="{link(key=newkey)}" class="purple_tlacitko" title="{i18n.t('Vygenerovat jiné pokračování')}"></a>'''
    else:
        newkeyline = ''

    # scenic or character
    line = line.strip()
    if PAGE == 'syn':
        is_scenic = True
    elif line.startswith('['):
        is_scenic = True
        line = line[1:]
        if line.endswith(']'):
            line = line[:-1]
    elif ':' in line:
        is_scenic = False
    else:
        is_scenic = True

    if is_scenic:
        class_titulek = 'titulek ital'
        if prompt:
            class_okenko = 'okenko'
            if PAGE in ('welcome1', 'script'):
                character = i18n.t('Scéna')
            else:
                character = i18n.t('Název hry')
        else:
            class_okenko = 'okenko_syn_running'
            character = ''
    else:
        class_okenko = 'okenko'
        class_titulek = 'titulek'
        character, line = line.split(':', 1)
        line = line.strip()

    # end of text
    if EOT in line:
        is_eot = True
        line = line[:line.index(EOT)]
    else:
        is_eot = False

    # print out the line
    if line:
        print(f'''
                    <div class='mom'>
                        <div class="{class_titulek}">
                            <p>{html.escape(character)}</p>
                        </div>
                        <div class="{class_okenko}">
                            <p>{html.escape(line)}</p>
                        </div>
                        {newkeyline}
                    </div>
''')
    else:
        is_partial = True
        print(f'''
                    <div class='mom'>
                        <div class="{class_titulek}">
                            <p>{html.escape(character)}</p>
                        </div>
                    </div>
''')


    if is_eot:
        print(f'''
                <div class='mom'>
                    <div class="titulek">
                        <p></p>
                    </div>
                    <div class="okenko">
                        <p><strong>{i18n.t('KONEC')}</strong></p>
                    </div>
                </div>
''')

    return is_eot, is_partial

def json_or_error(req, message='Error'):
    """Get JSON from requests response, or return {'error': message}"""
    if req.ok and req.json():
        return req.json()
    else:
        return {'error': f'{message}: {req.status_code} {req.reason} {req.text}'}

def query_list_scenes(server_addr=SERVER_ADDR):
    req = requests.post(
            server_addr,
            json={
                'list_scenes': 1,
                'username_limit': username_display
                }
            )
    return json_or_error(req, 'Could not list the scenes')

def query_display_scene(key, server_addr=SERVER_ADDR):
    if '-' not in key:
        key += '-'
    req = requests.post(
            server_addr,
            json={
                'key': key,
                'username': username_display
                }
            )
    return json_or_error(req, f'Could not display scene {key}')

def query_add_human_input(human_input, key, input_type='human', server_addr=SERVER_ADDR):
    if '-' not in key:
        key += '-'
    if input_type == 'syn_line':
        human_input = '[' + human_input + ']'
    elif input_type == 'char_name':
        human_input = human_input.rstrip()
        if not human_input.endswith(':'):
            human_input += ':'
    human_input = '\n' + human_input
    req = requests.post(
            server_addr, json={
                'human_input': human_input,
                'key': key,
                'username': username_display,
                'input_type': input_type}
            )
    return json_or_error(req, f'Could not display scene {key}')

# clean string obtained from input
def cl(s):
    s = s.strip()
    if s.endswith(':'):
        s = s[:-1]
    return s


def fix_diacritics(text):
    data = {'data': text, 'model': 'czech-diacritics_generator', 'suggestions': 1}
    req = requests.post('http://lindat.mff.cuni.cz/services/korektor/api/suggestions', data)
    if req.ok:
        return ''.join([chunk[-1] for chunk in req.json()['result']])
    else:
        logging.error(r'Korektor error: {req.status_code} {req.reason}')
        return text

def sentence_split(text):
    """Split text into a list of sentences."""
    url = 'http://lindat.mff.cuni.cz/services/udpipe/api/process'
    params = { 'tokenizer': 1,
            'output': 'plaintext=normalized_spaces',
            'data': text}
    response = requests.post(url, data = params)
    if response.ok:
        response.encoding='utf8'
        return [s for s in response.json()['result'].split('\n') if s]
    else:
        # Simple backup in case it fails
        logging.error(r'Sentence split error: {response.status_code} {response.reason}')
        return [s.strip()+'.' for s in text.split('.') if s.strip()]

def query_add_scene(prompt, char1=None, line1=None, char2=None, line2=None,
        outline=None, key=None, server_addr=SERVER_ADDR):
    """Insert into DB

    Diacritics get automatically added to prompt.
    TODO dont do this if input is in English!!!!
    So for now turned off!!!
    TODO move this probably into the server part which already does language
    detection!!!

    Outline, if defined, gets split into sentences separated by newlines.

    Key defaults to username, leading to keys such as 'demo_user_123-10a...'m
    but can be set especially to synopsis key to get keys such as
    'demo_user_123_10ab2a-10a...'

    Returns a JSON with 'key' of the inserted scene or 'error'."""

    # Prompt with character lines if specified
    text = ''
    if prompt:
        text += cl(prompt) + '\n\n'
    if line1:
        if char1:
            text += cl(char1) + ': '
        text += cl(line1) + '\n\n'
    if line2:
        if char2:
            text += cl(char2) + ': '
        text += cl(line2)

    if outline:
        outline = '\n'.join(sentence_split(outline))
    else:
        outline = None

    if not key:
        key = username_insert

    # TODO do this but only for Czech input !!!
    # text = fix_diacritics(text)

    # by default, char1 will speak the next generated line
    if char1 and line1 and not line2:
        # if only char1 is specified, char2 should speak now (and char1 after
        # him); because the backend is going to generate a line by char1 now,
        # we need to switch char1 and char2
        char1, char2 = char2, char1

    # add the scene into DB
    req = requests.post(server_addr, json={
            'scene': text,
            'key': key,
            'username': username_insert,
            'outline': outline,
            'char1': char1,
            'char2': char2,
            })

    return json_or_error(req, f'Could not save scene')

def send_email(address, scene):
    if address:
        # TODO the joining should be more clever for split lines containing
        # character names separately
        # TODO substitute endoftext by KONEC
        scene_text = scene[L_+'prompt'] + "\n***\n" + "\n".join(scene[L_+'lines'])
        compressed_key = compress_key(scene['key'])
        mail_text = f"""To: {address}
From: THEaiTRobot <noreply@ufallab.ms.mff.cuni.cz>
Subject: THEaiTRE {i18n.t('vygenerovaná scéna')} ({compressed_key})

{scene_text}

---
{i18n.t('Více o projektu')}: https://theaitre.com/
"""
        res = subprocess.run(["/usr/sbin/sendmail", "-t"], input=mail_text, encoding='UTF-8')
        if res.returncode == 0:
            return {'sent_email': True}
        else:
            return {'error': f'Sending mail failed: {res.returncode} {res.stderr}'}
    else:
        return {'sent_email': False}

def switch_language():
    global LANGUAGE
    if LANGUAGE == 'cs':
        LANGUAGE = 'en'
    else:
        LANGUAGE = 'cs'
    i18n.set('locale', LANGUAGE)

def process_query(args):
    """Main working method for querying the server"""

    # Intro and welcome pages
    if PAGE == 'intro':
        return {}
    else:
        # Using either the synopsis server or the base server
        if PAGE in ('welcome2', 'syn'):
            server_addr = SERVER_ADDR_SYN
        else:
            server_addr = SERVER_ADDR

        if PAGE in ('welcome1', 'welcome2'):
            return query_list_scenes(server_addr)
        else:
            assert PAGE in ('script', 'syn', 'syn2script')

    # Generating pages
    if 'add' in args:
        # Add a new scene
        if PAGE == 'syn2script':
            # For syn2script we first need to get the data from syn DB
            synopsis_data = query_display_scene(args.get('key'), SERVER_ADDR_SYN)
            if 'error' in synopsis_data:
                return synopsis_data
            # the title, in English
            args['prompt'] = synopsis_data['prompt']
            # all lines up to EOT, in English
            args['outline'] = '\n'.join(synopsis_data['lines']).split(EOT)[0].strip()
        # Insert a new scene into DB and get its key
        insertion_result = query_add_scene(
                args.get('prompt'),
                args.get('char1'), args.get('line1'),
                args.get('char2'), args.get('line2'),
                args.get('outline'),
                args.get('key'),
                server_addr)
        # We get 'key' or 'error'
        if 'error' in insertion_result:
            return insertion_result
        else:
            key = insertion_result.get('key')
    elif 'human_input' in args:
        # Insert synopsis line or character name
        assert PAGE == 'syn2script'
        insertion_result = query_add_human_input(
                args.get('human_input'),
                args.get('key'),
                args.get('input_type'),
                server_addr)
        # We get 'key' or 'error'
        if 'error' in insertion_result:
            return insertion_result
        else:
            key = insertion_result.get('key')
            if args.get('input_type') == 'char_name':
                # + generate line
                key += 'a'
    else:
        key = args.get('key')

    # Get scene
    result = query_display_scene(key, server_addr)
    if 'error' in result:
        return result
    else:
        result.update( send_email(args.get('email_address'), result) )
        return result


#
# *** main ***
#

try:
    data = process_query(args)
except Exception:
    data = {'error': traceback.format_exc()}

KEY = data.get('key')
print_header()

if DOWN:
    print(f'''<h1>{i18n.t('THEaiTRobot je dočasně mimo provoz')}</h1>''')
elif 'error' in data:
    logging.warning(data['error'])
    print(f'''<h1>{i18n.t('THEaiTRobot narazil na problém')}</h1>''')
    print("<pre>\n" + data['error'] + "\n</pre>")
elif PAGE in ('welcome1', 'welcome2'):
    # listing scenes
    print_index_header()
    scene_keys = sorted(data['scenes'].keys())
    for index, scene_key in enumerate(scene_keys):
        print_index_block(
                data['scenes'][scene_key][L_+'prompt'],
                scene_key,
                scene_keys[index-1],
                scene_keys[(index+1) % len(scene_keys)],
                index)
    print_insert_form()
    print_about_project()
    print_logos()
elif PAGE in ('script', 'syn', 'syn2script'):
    is_partial = False
    # print prompt lines
    for line in data[L_+"prompt"].split('\n'):
        if line.strip():
            print_line(line, prompt=True)
    # print generated lines
    is_eot = False
    if data[L_+'lines']:
        # print all lines except the last
        buf = ''
        lines_after = len(data[L_+'lines'])
        for line in data[L_+'lines'][:-1]:
            lines_after -= 1
            if line.strip():
                if line.strip().endswith(':'):
                    # Just a character name: prepend to next line
                    buf += line
                else:
                    if REGENERATE_FOR_EACH_LINE:
                        is_eot, is_partial = print_line(buf + line, newkey=get_newkey(data['key'][:-lines_after]))
                    else:
                        is_eot, is_partial = print_line(buf + line)
                    if is_eot:
                        break
                    buf = ''
        # print last line with regenerate button
        if not is_eot:
            is_eot, is_partial = print_line(buf + data[L_+'lines'][-1], get_newkey(data['key']))
    print_controls(data, is_eot, is_partial)
    print_generate_footer(data['key'], data['sent_email'])
else:
    assert PAGE == 'intro'
    # intro in EN
    print_intro()
    # intro in CS
    switch_language()
    print_intro()
    print('</div>')
    # logos in EN
    switch_language()
    print_logos()

# footer
print_footer()
