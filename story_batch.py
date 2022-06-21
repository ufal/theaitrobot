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
from keyops import compress_key, expand_key
from cgi_common import *

SERVER_ADDR, API_ADDR = load_config('config.json')
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
        return f'<a href="?id={newkey}" class="{css_class}" onclick="typing();">&lt; </a>'
    else:
        # already at first option
        return '<span class="backlink"></span>'


def batch_newlink(key):
    key = expand_key(key)
    prefix = key[:-1]
    current = key[-1]
    new = chr(ord(current) + 1)
    if new in string.ascii_lowercase:
        newkey = compress_key(prefix + new + batch_start)
        return '<a href="?id=' + newkey + '" class="newlink" onclick="typing();">X </a>'
    else:
        # already at 26th option or at human input (use backlink only)
        return '<span class="newlink"></span>'


def load_cookie_username():
    username = ''
    if 'HTTP_COOKIE' in os.environ:
        c = http.cookies.SimpleCookie(os.environ['HTTP_COOKIE'])
        if 'username' in c:
            username = c['username'].value
    return username


EOT = '<|endoftext|>'


def print_line(line, key):
    # Contains '<|endoftext|>'
    is_eot = EOT in line

    # Is human input
    is_hi = key[-1].isupper()

    # &#65279; is a zero-width non-break space, otherwise Chrome renders this wrongly
    hi1 = '&#65279;<span class="human_input">' if is_hi else ''
    line = html.escape(line[:line.index(EOT)]) if is_eot else html.escape(line)
    back = batch_backlink(key)
    new = batch_newlink(key)
    # TODO enable if wanted
    human = ''
    humanform = ''
    # human = '' if is_eot else human_input_link(key)
    # humanform = '' if is_eot else human_input_form(key)
    hi2 = '</span>' if is_hi else ''
    end = '\n<div class="theend">THE END</div>' if is_eot else ''

    print("<div class='left'><pre class='lines'>",
          f"{hi1}{line} {back} {new} {human}{end}{hi2}",
          f"</pre>{humanform}</div>",
          sep='\n')

    return is_eot


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

    # adding a scene
    if 'add' in args:
        # user just wants to add a new scene, nothing filled-in yet -> display the form
        if 'insert' not in args:
            return {'add': True}, username
        # processing a fully completed form (user added a new scene)
        # fill missing values
        if 'prompt' not in args:
            args['prompt'] = ''
        if 'id' not in args:
            if args['prompt']:
                args['id'] = args['prompt'].split('\n')[0]
            else:
                args['id'] = 'empty_prompt'
        if 'outline' not in args:
            args['outline'] = None
        if 'char1' not in args:
            args['char1'] = ''
        if 'char2' not in args:
            args['char2'] = ''
        if 'prev_summary' in args:
            args['prompt'] = f"{args['prev_summary']}\n\n\n{args['prompt']}"
        # the user may specify first character lines
        if 'line1' in args or 'line2' in args:
            # for simplicity, let's make sure input is sane
            if args['char1'] == '':
                args['char1'] = 'Man'
            if args['char2'] == '':
                args['char2'] = 'Woman'
            # appending to non-empty prompt with empty line
            if args['prompt'] != '':
                args['prompt'] += '\n\n'
            # line2 specified, line1 not: switch
            if 'line1' not in args:
                args['char1'], args['char2'] = args['char2'], args['char1']
                args['line1'] = args['line2']
                del args['line2']
            if 'line1' in args and 'line2' in args:
                args['prompt'] = (
                        f"{args['prompt']}"
                        f"{args['char1']}: {args['line1']}\n\n"
                        f"{args['char2']}: {args['line2']}"
                        )
            else:
                assert 'line1' in args and 'line2' not in args
                args['prompt'] = (
                        f"{args['prompt']}"
                        f"{args['char1']}: {args['line1']}"
                        )
                # server will make char1 speak now, so we need to switch them
                args['char1'], args['char2'] = args['char2'], args['char1']

        # insert
        req = requests.post(SERVER_ADDR, json={
            'key': args['id'], 'scene': args['prompt'],
            'char1': args['char1'], 'char2': args['char2'],
            'username': username, 'outline': args['outline']})
        if req.status_code != 200 or not req.json():
            raise Exception(f'Could not save scene, code: {req.status_code}, text: {req.text}')
        key = req.json()['key']  # get the key under which it was saved
        key = key + ('-' if '-' not in key else '')
        req = requests.post(SERVER_ADDR, json={'key': key + batch_start, 'username': username})  # try to display the scene


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

    # get the given scene
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

    # get a listing of scenes by the current user
    elif 'my_scenes' in args:
        req = requests.post(SERVER_ADDR, json={'list_scenes': 1, 'username_limit': username})

    # get a listing of all scenes
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
page_title = 'THEaiTRobot'
if 'key' in data:
    page_title += ": Scene %s</title>" % data['key'].split('-')[0]
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
    page_title += ': Add new scene'
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

# listing a scene with continuations
if 'key' in data:
    print(f"<p>Scene key: <a href=\"?id={compress_key(data['key'])}\">{compress_key(data['key'])}</a></p>")

    data['key'] = expand_key(data['key'])
    num_lines = len(data['lines'])
    prefix = len(data['key']) - num_lines

    # TODO reanble if needed
    human_input = ''
    # human_input = human_input_link(data['key'][:prefix])
    print("<div class='left'><pre id='prompt'>\n" + html.escape(data['prompt']) + human_input + "\n</pre></div>")
    if 'cs_prompt' in data:
        print("<div class='right'><pre id='prompt_tr'>\n" + html.escape(data['cs_prompt']) + "\n</pre></div>")
    clear()
    if 'outline' in data and data['outline']:
        print("<div class='left'><pre id='outline'>Outline:\n" + html.escape(data['outline']) + "\n</pre></div>")
        if 'cs_outline' in data and data['cs_outline']:
            print("<div class='right'><pre id='outline_tr'>Outline:\n" + html.escape(data['cs_outline']) + "\n</pre></div>")
        clear()

    is_eot = False
    for i in range(num_lines):
        is_eot = print_line(data['lines'][i], data['key'][:prefix + i + 1])
        if 'cs_lines' in data:
            print_tr_line(data['cs_lines'][i], is_eot)
        clear()
        if is_eot:
            break

    print_rating_links(data['key'], data['rating'])
    if not is_eot:
        print('<p class="clear"><a href="?id=' + compress_key(data['key'] + batch_start) + '" onclick="typing();">Continue this dialogue</a>\n</p>')

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
    print('<a href="?add=1">Add a new scene</a>&nbsp;')
    print('<a href="?search=1">Search in generated</a>&nbsp;')
    print(f'<form style="display: inline;" method="post" action="?">Username: <input type="text" id="username_box" name="username" value="{username}">'
          + '<input type="submit" name="change_username" value="Change"></form>')
    # list the scenes
    for scene_key in sorted(data['scenes'].keys()):
        print("<hr>\nScene ID: " + scene_key)
        if data['scenes'][scene_key].get('username'):
            print(" (added by " + data['scenes'][scene_key]['username'] + ")")
        print("\n<br>\n")
        print("<pre id='prompt'>" + html.escape(data['scenes'][scene_key]['prompt']) + "</pre>")
        print('<a href="?id=' + scene_key + '-' + compress_key(batch_start) + '"  onclick="typing();">Explore this scene</a>')

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
    Username: {username}
    <br><br>

    Summary of previous scene (optional; becomes part of the input)<br>
    <textarea name="prev_summary" cols="50" rows="10"></textarea>
    <br><br>

    Title (optional; becomes part of the input)<br>
    <input type="text" name="prompt" size="100" autofocus>
    <br><br>

    1st character (says the first line): first line (optional)<br>
    <input type="text" name="char1"  size="28"  value="Man">:
    <input type="text" name="line1"  size="200" value="">
    <br><br>

    2nd character (says the second line): second line (optional)<br>
    <input type="text" name="char2"  size="28" value="Woman">:
    <input type="text" name="line2"  size="200" value="">
    <br><br>

    <input type="hidden" name="insert" value="1">
    <input type="submit" name="add" value="Submit" onclick="typing();">
</form>
<hr>
<a href="?">Back to main</a>
          ''')

# footer
print("</body>")
print("</html>")
