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
from keyops import compress_key, expand_key, split_into_parts
from cgi_common import *
from collections import defaultdict

SERVER_ADDR, API_ADDR = load_config('config.json')
DOWN = False

def batch_discardlink(key):
    return '<a href="?id=' + key + '" class="discardlink" onclick="typing();" title="Discard and stop">X </a>'

# character to mark a regenerated line
REG = '~'
def batch_reglink(key, position):
    '''Get link with this line regenerated.

    E.g. aaaaa, 2 -> aaaaa2~'''
    command = str(position) + REG
    return '<a href="?id=' + key + command + '" class="newlink" onclick="typing();" title="Regenerate this line, keep following lines">↻ </a>'

# character to mark a cut line
CUT='_'
def batch_cutlink(key, position, is_continuation_line):
    '''Get link with this line cut away.

    E.g. aaaaa, 2 -> aaaaa2_'''
    command = str(position) + CUT
    if is_continuation_line:
        # also discard the prev line
        command = str(position-1) + CUT + command
    return '<a href="?id=' + key + command + '" class="cutlink" onclick="typing();" title="Cut this line, keep following lines">✂ </a>'

# character to mark an added line
ADD='.'
def batch_addlink(key, position):
    '''Get link with a line added after this line.

    E.g. aaaaa, 2 -> aaaaa2.'''
    command = str(position + 1) + ADD
    return '<a href="?id=' + key + command + '" class="addlink" onclick="typing();" title="Generate a new line after this line, keep following lines">+ </a>'

def load_cookie_username():
    username = ''
    if 'HTTP_COOKIE' in os.environ:
        c = http.cookies.SimpleCookie(os.environ['HTTP_COOKIE'])
        if 'username' in c:
            username = c['username'].value
    return username

def get_discard_key(fullkey, position, total_lines):
    result = [fullkey]
    for cut_position in range(position, total_lines):
        result.append(str(cut_position) + CUT)
    return ''.join(result)

EOT = '<|endoftext|>'

def print_line(line, cs_line, fullkey, position, total_lines, is_continuation_line):
    """Print a script line.

    line is the string line to print,
    fullkey = full key of current script,
    position = 0-based position of this line,
    total_lines = total number of lines,
    is_continuation_line = is actually two lines joined"""

    # TODO keep a list of bools indicating which lines are human input so that
    # we can mark them as such here?
    # Also we do not want to allow regenerating or cutting lines inserted from
    # the generated synopsis...

    # Contains '<|endoftext|>'
    is_eot = EOT in line

    line = html.escape(line[:line.index(EOT)]) if is_eot else html.escape(line)

    # discard including this
    discard = batch_discardlink(get_discard_key(fullkey, position, total_lines))

    reg = batch_reglink(fullkey, position)
    add = batch_addlink(fullkey, position)
    cut = batch_cutlink(fullkey, position, is_continuation_line)

    # keep this, discard after
    human_key = get_discard_key(fullkey, position+1, total_lines)
    human = '' if is_eot else human_input_link(human_key)
    humanform = '' if is_eot else human_input_form(human_key)

    end = '\n<div class="theend">THE END</div>' if is_eot else ''

    # &#65279; is a zero-width non-break space, otherwise Chrome renders this wrongly
    print("<div class='left'><pre class='lines'>",
          f'&#65279;<span>{line} {discard}{reg}{add}{cut}{human}{end}</span>',
          f"</pre>{humanform}</div>",
          sep='\n')

    # Translation
    if cs_line:
        if EOT in cs_line:
            cs_line = cs_line[:cs_line.index(EOT)]
        cs_line = html.escape(cs_line)
        cs_end = '\n<div class="theend">KONEC</div>' if is_eot else ''

        print("<div class='right'><pre class='lines'>",
            f"{cs_line}{cs_end}",
            "</pre></div>",
            sep='\n')

def clear():
    print('<div class="clear"></div>')


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

def sentence_split(text):
    """Split text into a list of sentences."""

    # curl --data 'tokenizer=&output=plaintext=normalized_spaces&data=Děti pojedou k babičce. Už se těší.'

    url = 'http://lindat.mff.cuni.cz/services/udpipe/api/process'
    params = { 'tokenizer': 1,
            'output': 'plaintext=normalized_spaces',
            'data': text}
    response = requests.post(url, data = params)
    if response.ok:
        response.encoding='utf8'
        return [s for s in response.json()['result'].split('\n') if s]
    else:
        # Simple backup in case it fals; TODO log error somehow
        return [s.strip()+'.' for s in text.split('.') if s.strip()]

def process_query(args):
    """Main working method for querying the server"""

    if 'change_username' in args:
        username = args.get('username', '')
    else:
        username = load_cookie_username()

    # adding a synopsis
    if 'add' in args:
        if 'prompt' in args and 'id' not in args:
            args['id'] = args['prompt'].split('\n')[0]
        if 'username' in args and args['username']:
            username = args['username']
        if 'prompt' in args and 'id' in args:
            # add the synopsis into DB
            if 'outline' not in args:
                raise Exception(f'Could not save synopsis, no synopsis specified!')
            outline = '\n'.join(sentence_split(args['outline']))
        if args['add'] == '2':
            # processing a fully completed form (user added a new synopsis)
            req = requests.post(SERVER_ADDR, json={'key': args['id'], 'scene': args['prompt'], 'username': username, 'outline': outline})
            if req.status_code != 200 or not req.json():
                raise Exception(f'Could not save synopsis, code: {req.status_code}, text: {req.text}')
            key = req.json()['key']  # get the key under which it was saved
            key = key + ('-' if '-' not in key else '')
            req = requests.post(SERVER_ADDR, json={'key': key, 'username': username})  # try to display the scene
        else:
            # user just wants to add a new synopsis, nothing filled-in yet -> display the form
            return {'add': '1',
                    'id': args['id'],
                    'prompt': args['prompt'],
                    'outline': outline}, username

    # adding a human input at the given point in the play
    elif 'human_input' in args:
        key = args.get('id', args.get('key'))
        key = key + ('-' if '-' not in key else '')
        human_input = args['human_input']
        input_type = args.get('input_type', 'human')
        cont_key = '' if input_type == 'synopsis' else 'a'
        if input_type == 'character':
            human_input = human_input.rstrip()
            if not human_input.endswith(':'):
                human_input += ':'
        # preserve preceding space of the original line we're replacing, if set to do so
        if args.get('use_pre_space'):
            human_input = args.get('pre_space', '') + human_input
        # store the input
        req = requests.post(SERVER_ADDR, json={'human_input': human_input, 'key': key, 'username': username, 'input_type': input_type})
        if req.status_code != 200 or not req.json():
            raise Exception(f'Could not add human input, code: {req.status_code}, text: {req.text}')
        key = req.json()['key']  # get the key under which the input was stored
        req = requests.post(SERVER_ADDR, json={'key': key + cont_key, 'username': username})  # generate continuation
        requests.post(SERVER_ADDR, json={'pregenerate': key + cont_key + 'a'})  # and pregenerate even more

    # DB search
    elif 'search' in args:
        # we have the search query
        if 'query' in args:
            req = requests.post(SERVER_ADDR, json={'search': args['search'], 'query': args['query']})
        # user just want to search, display the search form
        else:
            return {'search': True}, username

    # get the given scene
    elif 'id' in args or 'key' in args:
        key = args.get('id', args.get('key'))
        key = key + ('-' if '-' not in key else '')
        req = requests.post(SERVER_ADDR, json={'key': key, 'username': username})
        requests.post(SERVER_ADDR, json={'pregenerate': key + 'a'})

    # get a listing of recently generated IDs by the current user
    elif 'my_recent' in args:
        req = requests.post(SERVER_ADDR, json={'recent': int(args['my_recent']), 'username_limit': username})

    # get a listing of all recently generated IDs
    elif 'recent' in args:
        req = requests.post(SERVER_ADDR, json={'recent': int(args['recent'])})

    # get a listing of scenes by the current user which have a non-empty outline
    elif 'my_scenes' in args:
        req = requests.post(SERVER_ADDR, json={'list_scenes': 1, 'username_limit': username, 'outline_limit': 1})

    # get a listing of all scenes which have a non-empty outline
    else:
        req = requests.post(SERVER_ADDR, json={'list_scenes': 1, 'outline_limit': 1})

    # try to return the result, fail gracefully
    try:
        assert req.status_code == 200
        ret = req.json()
    except:
        return {'error': f'Request error -- code: {req.status_code}, text: {req.text}'}, username
    # user requested plaintext download instead of normal listing -- just add this info to the results
    if 'key' in ret and 'download' in args:
        ret['download'] = 1
    return ret, username


#
# *** main ***
#

#
# get required stuff from server
#

try:
    data, username = process_query(cgi_to_dict(cgi.FieldStorage()))
except Exception:
    data = {'error': traceback.format_exc()}
    username = load_cookie_username()

#
# now print it out
#

# special case: plaintext download of generated outputs
if 'download' in data:
    print("Content-Type: text/plain; charset=UTF-8")
    # divide header from content
    print()
    print('** ID: ' + compress_key(data['key']) + '\n\n')
    print('** Prompt:\n' + data['prompt'] + '\n---')
    # handle EOT characters
    try:
        # if an EOT character is present, truncate the remaining lines
        data['lines'] = data['lines'][0:[(EOT in l) for l in data['lines']].index(True) + 1]
        data['cs_lines'] = data['cs_lines'][:len(data['lines'])]
        # remove the ugly EOT token from the last line
        data['lines'][-1] = data['lines'][-1].replace(EOT, '')
        data['cs_lines'][-1] = data['cs_lines'][-1].replace(EOT, '')
        # ... and replace it with a nicer one
        data['lines'].append('--THE END--')
        data['cs_lines'].append('--KONEC--')

    # EOT not found in the text -> don't do anything
    except ValueError:
        pass
    print('** Lines:\n' + '\n'.join(data['lines']) + '\n\n')
    print('** Czech prompt:\n' + data['cs_prompt'] + '\n---')
    print('** Czech lines:\n' + '\n'.join(data['cs_lines']) + '\n\n')
    # finish here -- don't print any HTML
    quit()

# decide on page title
page_title = 'THEaiTRobot (syn2script)'
if 'key' in data:
    page_title += ": Scene %s" % data['key'].split('-')[0]
elif 'scenes' in data:
    page_title += ': Scene listing'
    if 'username' in data:
        page_title += ' for user ' + data['username']
elif 'recent' in data:
    page_title += ': Recently generated'
    if 'username' in data:
        page_title += ' by user ' + data['username']
elif 'error' in data:
    page_title += ': Error'
elif 'add' in data:
    page_title += ': Add new synopsis'
elif 'search' in data:
    page_title += ': Search'


# print HTTP header
print("Content-Type: text/html; charset=UTF-8")
c = http.cookies.SimpleCookie()
c['username'] = username
if username:  # set username cookie for 1 year
    c['username']['max-age'] = 31556952
else:  # unset username -> expiration in the past -> delete cookie
    c['username']['expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
print(c.output())
# divide header from content
print()

# print HTML header
print_html_head(page_title, username, data, API_ADDR)

if 'key' in data:
    # Script generating screen
    print('<body onunload="notyping()" onload="window.scrollTo(0,document.body.scrollHeight);">')
else:
    print('<body onunload="notyping()">')

print('<div id="graydiv"></div>')

print('''
<div id="typingdiv">
<div id="horizontaldiv">
<img id="typingimg" src="robot.gif">
</div>
</div>
''')

# print HTML body
print("""<div style="padding: 1px 1px 1px 1px">
        <a href="http://www.theaitre.com">
        <img src="https://www.theaitre.com/wp-content/uploads/logo-1.png"
        style="float:left; margin-right: 1em; height: 30px">
        </a>
        <a href="http://www.tacr.cz">
        <img src="https://www.tacr.cz/logotypy/logo_TACR_zakl.png"
        style="float:left; margin-right: 1em; height: 30px">
        <img src="https://www.tacr.cz/logotypy/Eta.png" style="float:left; margin-right: 1em; height: 30px">
        </a>
        <p style="font-size: x-small; font-family: sans-serif">This project is co-financed with state support of Technological agency of the Czech Republic (Technologická agentura ČR)
within the Program ÉTA 3.</p>
</div><hr style="clear: both">""")
if DOWN:
    print(f"<h1>THEaiTRobot is temporarily unavailable</h1>")
    sys.exit()
print(f"<h1>{page_title}</h1>")

def command_form_key(text, button, key):
    command_form(f'<span style="width: 12ex; display: inline-block">{text}</span>',
            button, key, 'get')

def command_form_synopsis(text):
    command_form(
            f'[{html.escape(text)}] <input name="human_input" value="[{html.escape(text)}]" type="hidden">',
            '+', input_type='synopsis')

def command_form_character(text=''):
    command_form(
            f'<input name="human_input" value="{html.escape(text)}" placeholder="Write character name here:" size="25">',
            input_type='character')

# TODO pre_space now hardcoded to one newline
def command_form(text, button='&gt;', key='', method='post', input_type=None):
    key = compress_key(data['key'] + key)

    if input_type:
        other = f'''
        <input type="hidden" name="use_pre_space" value="1">
        <input type="hidden" name="pre_space" value="\n">
        <input type="hidden" name="input_type" value="{input_type}">'''
    else:
        other = ''

    print(f'''
    <form class="command" method="{method}" action="?">
        {text}
        {other}
        <input type="hidden" name="id" value="{key}">
        <input type="submit" value="{button}" class="button" onclick="typing();">
    </form>
''')

# TODO maybe this could be done better but maybe this good enough?
# TODO assumes we use entire lines, not e.g. cut into smaller pieces. This
# shall be ensured when creating the synopsis; it should be split into
# sentences so that there is no need to further split it into smaller chunks.
def find_first_unused_outline_line(lines, outline, prompt=''):
    """Find first outline line that has not been used yet."""
    if not outline:
        return None
    used = set( (line.strip() for line in lines) )
    for line in prompt.split('\n'):
        line = line.strip()
        if line:
            used.add(line)

    for line in outline.split('\n'):
        line = line.strip()
        if f'[{line}]' not in used:
            return line

    return None

def extract_characters(lines, prompt='', outline=''):
    """Get all character names.

    Order from most recent to least recent,
    always add Man and Woman to have something, switch first two.
    Gets all character names already used in the generated script.
    Also returns already_has_character_lines: True if lines already contain
    some lines said by some character ("Character: line"), False otherwise
    i.e. lines is empty or only contains scenic remarks etc.
    TODO:
    - Probably also try to extract character names from the synopsis using
    NER or something like that.
    - Probably also from prompt?
    """

    # All characters that appear in lines,
    # going in reverse order to have most recent characters first
    # (ordered because dicts are ordered in Python)
    characters = defaultdict(int)
    for line in reversed(lines):
        line = line.strip()
        colon_position = line.find(':')
        if colon_position != -1:
            # Character name including colon
            character = line[:colon_position+1]
            characters[character] += 1
    already_has_character_lines = bool(characters)

    # Always have these two
    characters['Man:'] += 1
    characters['Woman:'] += 1

    # Switch first two; it is most likely that the penultimate character
    # will speak now, not the one that has just spoken.
    # We are guaranteed to have at least two characters because of the two defaults.
    characters_list = list(characters.keys())
    characters_list[0], characters_list[1] = characters_list[1], characters_list[0]

    return characters_list, already_has_character_lines

# listing a scene with continuations
if 'key' in data:
    print(f"<p>Scene key: <a href=\"?id={compress_key(data['key'])}\">{compress_key(data['key'])}</a></p>")

    num_lines = len(data['lines'])

    is_eot = False

    # Prompt and Outline
    # TODO also provide human link and human form and add link?
    print(f'''<div class='left'><pre id='prompt'>
{html.escape(data['prompt'])}
</pre></div>''')
    if 'cs_prompt' in data:
        print("<div class='right'><pre id='prompt_tr'>\n" + html.escape(data['cs_prompt']) + "\n</pre></div>")
    clear()
    if 'outline' not in data:
        data['outline'] = ''
    if data['outline']:
        print("<div class='left'><pre id='outline'>Outline:\n" + html.escape(data['outline']) + "\n</pre></div>")
        if 'cs_outline' in data and data['cs_outline']:
            print("<div class='right'><pre id='outline_tr'>Outline:\n" + html.escape(data['cs_outline']) + "\n</pre></div>")
        clear()

    # Lines
    is_eot = False
    buffer_en, buffer_cs = '', ''
    for i in range(num_lines):
        line = data['lines'][i]
        cs_line = data['cs_lines'][i] if 'cs_lines' in data else ''

        is_eot = EOT in line

        if line:
            if i != num_lines-1 and not is_eot and line.endswith(':'):
                # non-last line is only a character name: prepend to next line
                buffer_en += line
                if cs_line:
                    buffer_cs += cs_line
            else:
                # standard line
                print_line(buffer_en + line, buffer_cs + cs_line, data['key'],
                        i, num_lines, (buffer_en != ''))
                buffer_en, buffer_cs = '', ''
                clear()
                if is_eot:
                    # endoftext in line: stop here
                    break

    assert buffer_en == ''

    # Rating
    print_rating_links(data['key'], data['rating'])

    # Commands
    # Let the given character speak
    # NOTE: prompt and outline currently ignored
    characters, already_has_character_lines = extract_characters(data['lines'], data['prompt'], data['outline'])
    outline_line = find_first_unused_outline_line(data['lines'], data['outline'], data['prompt'])
    # Output
    print('<div class="left" style="padding-top: 1em">')
    # Add a fully generated line or lines.
    # Avoid this if no character line is present in the script yet.
    # TODO this may change when we have a new synopsis2script model
    if not is_eot and already_has_character_lines:
        command_form_key('+1 line', button='&gt;', key='a')
        command_form_key('+10 lines', button='&gt;&gt;', key='10a')
        command_form_key('+20 lines', button='&gt;&gt;&gt;', key='20a')
    # Add a character line ("Character: line")
    for character in characters:
        command_form_character(character)
    command_form_character()
    # Add a line from outline ("[Scenic remark.]")
    if outline_line:
        command_form_synopsis(outline_line)

    print('</div>')
    clear()

    print(f"<hr>\n<a href=\"?\">Back to main</a>&nbsp; <a href=\"?id={compress_key(data['key'])}&amp;download=1\">Plaintext</a>")

# listing recent stuff
elif 'recent' in data:
    print_recent_list(username, data)

# listing scenes
elif 'scenes' in data:
    # always show link for global history
    print('<a href="?recent=0">All recently generated</a>&nbsp;')
    # username is set -> also show link for current user's history
    if username:
        print('<a href="?my_recent=0">My recently generated</a>&nbsp;')
    # we're listing current user's scenes -> show link to all scenes
    if 'username' in data:
        print('<a href="?">All scenes</a>&nbsp;')
    # we're listing all scenes & username is set -> show link to current user's scenes
    elif username:
        print('<a href="?my_scenes=1">My scenes</a>&nbsp;')
    print('<a href="synopse.py">Generate a new synopsis (klikátko na synopse)</a>&nbsp;')
    print('<a href="?search=1">Search in generated</a>&nbsp;')
    print(f'<form style="display: inline;" method="post" action="?">Username: <input type="text" name="username" value="{username}">'
          + '<input type="submit" name="change_username" value="Change"></form>')
    # list the scenes
    for scene_key in sorted(data['scenes'].keys()):
        print("<hr>\nScene ID: " + scene_key)
        if data['scenes'][scene_key].get('username'):
            print(" (added by " + data['scenes'][scene_key]['username'] + ")")
        print("\n<br>\n")
        print("<pre id='prompt'>" + html.escape(data['scenes'][scene_key]['prompt']) + "</pre>")
        print('<a href="?id=' + scene_key + '-' + '">Explore this scene</a>')

# showing errors
elif 'error' in data:
    print("<pre>\n" + data['error'] + "\n</pre>")
    print('<hr>\n<a href="?">Back to main</a>')

# searching and showing results
elif 'search' in data:

    # make sure the selection we used last time is preserved
    checked = {'prompt': '', 'cs_prompt': '', 'text': '', 'cs_text': ''}
    if data['search'] in checked:
        checked[data['search']] = "checked"
    # print search form
    print(f'''
<a href="?">Back to main</a><hr>
<form method="post" action="?">
<input type="radio" id="prompt" name="search" value="prompt" {checked['prompt']}><label for="prompt">English prompt</label>
<input type="radio" id="cs_prompt" name="search" value="cs_prompt" {checked['cs_prompt']}><label for="cs_prompt">Czech prompt</label>
<input type="radio" id="text" name="search" value="text" {checked['text']}><label for="text">English text</label>
<input type="radio" id="cs_text" name="search" value="cs_text" {checked['cs_text']}><label for="cs_text">Czech text</label>
&nbsp;Search query: <input type="text" name="query" value="{data.get('query', '')}">
<input type="submit" name="search_button" value="Submit" onclick="typing();">
<br>
Use "%" to represent any string, "_" to represent any character.
</form><hr>
''')
    # print search results
    if 'results' in data:
        print(f"Search results for <strong>{data['query']}</strong> within <strong>{data['search']}</strong>:")
        # columns to display
        if 'prompt' in data['search']:
            fields = ['timestamp', 'username', 'key', 'prompt']
        else:
            fields = ['timestamp', 'username', 'key', 'model', 'server_version', 'git_version', 'git_branch', 'text']
        if 'cs' in data['search']:
            fields[-1] = 'cs_' + fields[-1]

        print("<table>\n<tr>\n" + "\n".join([f"<th>{f}</th>" for f in fields]) + "\n</tr>\n")
        for result in data['results']:
            if 'git_version' in result:  # shorten git ids
                result['git_version'] = result['git_version'][:7]
            if 'key' in result:
                result['key'] = compress_key(result['key'])
                result['key'] = f"<a href=\"?id={result['key']}\">{result['key']}</a>"
            print("<tr>\n" + "\n".join([f"<td>{result.get(f, '')}</td>" for f in fields]) + "\n</tr>\n")
        print("</table>")

# adding new scene
elif 'add' in data and data['add'] == '1':
    print(f'''
<form method="post" action="?">
    Username: {username}<br>
    Script title: <input type="text" name="prompt" size="70" value="{html.escape(data['prompt'])}"><br>
    Synopsis:<br>
    <textarea name="outline" cols="70" rows="40">{html.escape(data['outline'])}</textarea><br>
    <input type="hidden" name="id" value="{compress_key(data['id'])}">
    <input type="hidden" name="username" value="{username}">
    <input type="hidden" name="add" value="2">
    <input type="submit" value="Submit" onclick="typing();">
</form>
<hr>
<a href="?">Back to main</a>
          ''')

# footer
print("</body>")
print("</html>")
