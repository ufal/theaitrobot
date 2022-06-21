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

SERVER_ADDR, API_ADDR = load_config('syn_config.json')
DOWN = False


batch_start = 'aaaaaaaaaa'


def batch_backlink(key):
    """Add link to previous chosen option from this point."""
    key = expand_key(key)
    prefix = key[:-1]
    current = key[-1]
    new = chr(ord(current) - 1)
    css_class = "backlink"
    if current == 'A':  # go to automatic stuff if coming back from humans (1st option cause we don't know how many there are)
        new = 'a'
        css_class = "backlink human"
    if new in string.ascii_letters:
        newkey = compress_key(prefix + new + batch_start)
        # NOTE: back link does not work well with cuts; but keeping it anyway
        return f'<a href="?id={newkey}" class="{css_class}" onclick="typing();">&lt; </a>'
        # return '<span class="backlink">&lt; </span>'
    else:
        # already at first option
        return '<span class="backlink"></span>'


def batch_newlink(key, preceding_cuts):
    key = expand_key(key)
    prefix = key[:-1]
    current = key[-1]
    new = chr(ord(current) + 1)
    if new in string.ascii_lowercase:
        newkey = compress_key(prefix + preceding_cuts + new + batch_start)
        return '<a href="?id=' + newkey + '" class="newlink" onclick="typing();" title="Throw away from this line and regenerate">X </a>'
    else:
        # already at 26th option or at human input (use backlink only)
        return '<span class="newlink"></span>'

# character to mark a cut line; is . OK?
CUT='_'
def batch_cutlink(fullkey, position):
    '''Get link with this line cut away.

    E.g. aaaaa, 2 -> aaaaa2_'''
    newkey = compress_key(fullkey + str(position) + CUT)
    return '<a href="?id=' + newkey + '" class="cutlink" onclick="typing();" title="Cut this line, keep following lines">✂ </a>'

def load_cookie_username():
    username = ''
    if 'HTTP_COOKIE' in os.environ:
        c = http.cookies.SimpleCookie(os.environ['HTTP_COOKIE'])
        if 'username' in c:
            username = c['username'].value
    return username


EOT = '<|endoftext|>'


def print_line(line, key, preceding_cuts, fullkey, position):
    """Print a script line, return if it contained end of text.

    line is the string line to print,
    key is the key of this line,
    preceding cuts = line indexes of preceding cut lines not yet reflected in
    key, already in a format of cut commands in a string,
    fullkey = full key of current script,
    position = 0-based position of this line"""
    # Contains '<|endoftext|>'
    is_eot = EOT in line

    # Is human input
    is_hi = key[-1].isupper()

    # &#65279; is a zero-width non-break space, otherwise Chrome renders this wrongly
    hi1 = '&#65279;<span class="human_input">' if is_hi else ''
    line = html.escape(line[:line.index(EOT)]) if is_eot else html.escape(line)
    back = batch_backlink(key)
    new = batch_newlink(key, preceding_cuts)
    cut = batch_cutlink(fullkey, position)
    # human input is disabled here
    # human = '' if is_eot else human_input_link(key + preceding_cuts)
    # humanform = '' if is_eot else human_input_form(key + preceding_cuts)
    hi2 = '</span>' if is_hi else ''
    end = '\n<div class="theend">THE END</div>' if is_eot else ''

    print("<div class='left'><pre class='lines'>",
          f"{hi1}{line} {back} {new} {cut} {end}{hi2}", # {human} removed before {end}
          f"</pre></div>", # {humanform} removed
          sep='\n')

    return is_eot

# NOTE: some cut back links may lead to unexpected places
def print_cut_line(lineindex, key):
    key_parts = split_into_parts(key)
    newkey = key_parts[0] + '-'  # scene_key-
    for part in key_parts[1:]:
        # remove the cut of lineindex
        if part != f'{lineindex}_':
            newkey += part
    print('<div class="left"><a href="?id=' + compress_key(newkey) + '" class="cutbacklink" onclick="typing();" title="Return back the cut line">--- ✂ ---</a></div>')

def print_tr_line(line, is_eot=False):
    is_eot = EOT in line

    line = html.escape(line[:line.index(EOT)]) if is_eot else html.escape(line)
    end = '\n<div class="theend">KONEC</div>' if is_eot else ''

    print("<div class='right'><pre class='lines'>",
          f"{line}{end}",
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


def process_query(args):
    """Main working method for querying the server"""

    if 'change_username' in args:
        username = args.get('username', '')
    else:
        username = load_cookie_username()

    # adding a synopsis
    if 'add' in args:
        # processing a fully completed form (user added a new synopsis)
        if 'prompt' in args and 'id' not in args:
            args['id'] = args['prompt'].split('\n')[0]
        if 'prompt' in args and 'id' in args:
            # add the synopsis into DB
            if 'outline' not in args:
                args['outline'] = None
            req = requests.post(SERVER_ADDR, json={'key': args['id'], 'scene': args['prompt'], 'username': username, 'outline': args['outline']})
            if req.status_code != 200 or not req.json():
                raise Exception(f'Could not save synopsis, code: {req.status_code}, text: {req.text}')
            key = req.json()['key']  # get the key under which it was saved
            key = key + ('-' if '-' not in key else '')
            req = requests.post(SERVER_ADDR, json={'key': key + batch_start, 'username': username})  # try to display the synopsis

        # user just wants to add a new synopsis, nothing filled-in yet -> display the form
        else:
            return {'add': True}, username

    # adding a human input at the given point in the play
    elif 'human_input' in args:
        key = args.get('id', args.get('key'))
        key = key + ('-' if '-' not in key else '')
        human_input = args['human_input']
        # preserve preceding space of the original line we're replacing, if set to do so
        if args.get('use_pre_space'):
            human_input = args.get('pre_space', '') + human_input
        # store the input
        req = requests.post(SERVER_ADDR, json={'human_input': human_input, 'key': key, 'username': username})
        if req.status_code != 200 or not req.json():
            raise Exception(f'Could not add human input, code: {req.status_code}, text: {req.text}')
        key = req.json()['key']  # get the key under which the input was stored
        req = requests.post(SERVER_ADDR, json={'key': key + batch_start, 'username': username})  # generate continuation
        requests.post(SERVER_ADDR, json={'pregenerate': key + 2 * batch_start})  # and pregenerate even more

    # DB search
    elif 'search' in args:
        # we have the search query
        if 'query' in args:
            req = requests.post(SERVER_ADDR, json={'search': args['search'], 'query': args['query']})
        # user just want to search, display the search form
        else:
            return {'search': True}, username

    # get the given synopsis
    elif 'id' in args or 'key' in args:
        key = args.get('id', args.get('key'))
        key = key + ('-' if '-' not in key else '')
        req = requests.post(SERVER_ADDR, json={'key': key, 'username': username})
        requests.post(SERVER_ADDR, json={'pregenerate': key + batch_start})

    # get a listing of recently generated IDs by the current user
    elif 'my_recent' in args:
        req = requests.post(SERVER_ADDR, json={'recent': int(args['my_recent']), 'username_limit': username})

    # get a listing of all recently generated IDs
    elif 'recent' in args:
        req = requests.post(SERVER_ADDR, json={'recent': int(args['recent'])})

    # get a listing of synopses by the current user
    elif 'my_scenes' in args:
        req = requests.post(SERVER_ADDR, json={'list_scenes': 1, 'username_limit': username})

    # get a listing of all synopses
    else:
        req = requests.post(SERVER_ADDR, json={'list_scenes': 1})

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
page_title = 'THEaiTRobot (syn)'
if 'key' in data:
    page_title += ": Synopsis %s</title>" % data['key'].split('-')[0]
elif 'scenes' in data:
    page_title += ': Synopsis listing'
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

# listing a synopsis with continuations
if 'key' in data:
    print(f"<p>Synopsis key: <a href=\"?id={compress_key(data['key'])}\">{compress_key(data['key'])}</a></p>")

    data['key'] = expand_key(data['key'])
    num_lines = len(data['lines'])
    key_parts = split_into_parts(data['key'])
    key_parts.reverse()

    print("<div class='left'><pre id='prompt'>\n" + html.escape(data['prompt']) + "\n</pre></div>")
    if 'cs_prompt' in data:
        print("<div class='right'><pre id='prompt_tr'>\n" + html.escape(data['cs_prompt']) + "\n</pre></div>")
    clear()
    if 'outline' in data and data['outline']:
        print("<div class='left'><pre id='outline'>Outline:\n" + html.escape(data['outline']) + "\n</pre></div>")
        if 'cs_outline' in data and data['cs_outline']:
            print("<div class='right'><pre id='outline_tr'>Outline:\n" + html.escape(data['cs_outline']) + "\n</pre></div>")
        clear()

    lines = list()
    # already cut lines not yet reflected in key
    preceding_cuts = set()
    key = key_parts.pop() + '-'  # scene_key-
    is_eot = False
    for i in range(num_lines):
        line = data['lines'][i]
        # Add cut commands
        while key_parts[-1].endswith(CUT):
            command = key_parts.pop()
            # Cut already part of key, remove from preceding cuts
            cut_index = int(command[:-1])
            preceding_cuts.remove(cut_index)
            # Add to key
            key += command
        # Add line character
        key += key_parts.pop()
        if line:
            # real line
            preceding_cuts_str = ''.join([f'{p}_' for p in preceding_cuts])
            is_eot = print_line(line, key, preceding_cuts_str, data['key'], i)
            if 'cs_lines' in data:
                print_tr_line(data['cs_lines'][i], is_eot)
            clear()

            if is_eot:
                lines.append(line[:line.index(EOT)])
                break
            else:
                lines.append(line)
        else:
            # cut line
            preceding_cuts.add(i)
            print_cut_line(i, data['key'])
            clear()
    lines = '\n'.join(lines)

    if not is_eot:
        print('<p class="clear"><a href="?id=' + compress_key(data['key'] + batch_start) + '" onclick="typing();">Continue this synopsis</a>\n</p>')

    print_rating_links(data['key'], data['rating'])

    print(f'''<form method="post" action="synopsis2script.py" class="synopsis2script">
        <input type="hidden" name="id" value="{compress_key(data['key'])}">
        <input type="hidden" name="prompt" value="{html.escape(data['prompt'])}">
        <input type="hidden" name="outline" value="{html.escape(lines)}">
        <input type="hidden" name="username" value="{username}">
        <input type="hidden" name="add" value="1">
        <input type="submit" value="Generate script from this synopsis">
    </form>''')

    print(f"<hr>\n<a href=\"?\">Back to main</a>&nbsp; <a href=\"?id={compress_key(data['key'])}&amp;download=1\">Plaintext</a>")

# listing recent stuff
elif 'recent' in data:
    print_recent_list(username, data)


# listing synopses
elif 'scenes' in data:
    # always show link for global history
    print('<a href="?recent=0">All recently generated</a>&nbsp;')
    # username is set -> also show link for current user's history
    if username:
        print('<a href="?my_recent=0">My recently generated</a>&nbsp;')
    # we're listing current user's synopses -> show link to all synopses
    if 'username' in data:
        print('<a href="?">All synopses</a>&nbsp;')
    # we're listing all synopses & username is set -> show link to current user's synopses
    elif username:
        print('<a href="?my_scenes=1">My synopses</a>&nbsp;')
    print('<a href="?add=1">Add a new synopsis</a>&nbsp;')
    print('<a href="?search=1">Search in generated</a>&nbsp;')
    print(f'<form style="display: inline;" method="post" action="?">Username: <input type="text" name="username" value="{username}">'
          + '<input type="submit" name="change_username" value="Change"></form>')
    # list the synopses
    for scene_key in sorted(data['scenes'].keys()):
        print("<hr>\nSynopsis ID: " + scene_key)
        if data['scenes'][scene_key].get('username'):
            print(" (added by " + data['scenes'][scene_key]['username'] + ")")
        print("\n<br>\n")
        print("<pre id='prompt'>" + html.escape(data['scenes'][scene_key]['prompt']) + "</pre>")
        print('<a href="?id=' + scene_key + '-' + compress_key(batch_start) + '"  onclick="typing();">Explore this synopsis</a>')

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
elif 'add' in data:
    print(f'''
<form method="post" action="?">
    Username: {username}<br>
    Synopsis title: <input type="text" name="prompt" size="50"><br>
    <input type="submit" name="add" value="Submit" onclick="typing();">
</form>
<hr>
<a href="?">Back to main</a>
          ''')

'''
    Synopsis ID: <input type="text" name="id"><br>
    Prompt text:<br>
    <textarea name="prompt" cols="50" rows="10"></textarea><br>
    Outline (optional, please submit one sentence per line):<br>
    <textarea name="outline" cols="50" rows="10"></textarea><br>
'''

# footer
print("</body>")
print("</html>")
