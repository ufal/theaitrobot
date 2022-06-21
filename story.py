#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cgi
import html
import requests
import traceback
import json

try:
    with open('config.json') as configfile:
        config = json.load(configfile)
        SERVER_ADDR = config['SERVER_ADDR']
except:
    SERVER_ADDR = 'http://localhost:8456'

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
    # adding a scene
    if 'add' in args:
        # processing a fully completed form (user added a new scene)
        if 'prompt' in args and 'id' in args:
            # add the scene into DB
            req = requests.post(SERVER_ADDR, json={'key': args['id'], 'scene': args['prompt']})
            if req.status_code != 200:
                raise Exception('Could not save scene, code: {req.status_code}, text: {req.text}')
            # get a listing of scenes
            req = requests.post(SERVER_ADDR, json={'list_scenes': 1})
        # user just wants to add a new scene, nothing filled-in yet -> display the form
        else:
            return {'add': True}
    # get the given scene
    elif 'id' in args or 'key' in args:
        key = args.get('id', args.get('key'))
        key = key + ('-' if '-' not in key else '')
        req = requests.post(SERVER_ADDR, json={'key': key})
    # get a listing of scenes
    else:
        req = requests.post(SERVER_ADDR, json={'list_scenes': 1})
    if not req.json():
        return {'error': 'Request error -- code: {req.status_code}, text: {req.text}'}
    return req.json()


def is_bad_line(line):
    return len(set(line)) < 4

import difflib
def is_novel(line,history):
    """
    checks whether line is not too similiar from history
    """
    ratios = map(lambda x: difflib.SequenceMatcher(None,line,x),history)
    return not any(r < 0.92 for r in list(ratios))



#
# *** main ***
#

#
# get required stuff from server
#
try:
    data = process_query(cgi_to_dict(cgi.FieldStorage()))
except Exception:
    data = {'error': traceback.format_exc()}

#
# now print it out
#

# decide on page title
page_title = 'Theaitre'
if 'key' in data:
    page_title = "Scene %s</title>" % data['key'].split('-')[0]
elif 'scenes' in data:
    page_title = 'Scene listing'
elif 'error' in data:
    page_title = 'Error'
elif 'add' in data:
    page_title = 'Add new scene'


# print HTTP header
print("Content-Type: text/html; charset=UTF-8\n")

# print HTML header
print('<!DOCTYPE html>\n<html lang="en">')

print('<head>\n<meta charset="utf-8">')
print(f"<title>{page_title}</title>")

print("""<style>

pre {
padding: 0px 1em 0px 1em;
font-size: large;
white-space: pre-wrap;
}

#prompt {
background-color: #eee;
display: table;
margin-bottom: 0px;
}

#prompt_tr {
background-color: #ddd;
display: table;
margin-bottom: 0px;
}

.left {
float: left;
width: 50%;
}

.right {
float: right;
width: 50%;
}

.left pre {
/*background-color: #ccf;*/
display: table;
margin-right: 1em;
}

.right pre {
/*background-color: #fcc;*/
display: table;
margin-left: 1em;
}

.clear {clear: both}

#lines {
margin-top: 0px
}

#typingimg {
width: 480px;
height: 360px;
}

#typingdiv {
position: fixed;
top: 0px;
left: 0px;
width: 100%;
height: 100vh;
display: none;
align-items: center;
}

#horizontaldiv {
margin-left: auto;
margin-right: auto;
text-align: center;
display: block;
}

#graydiv {
position: fixed;
top: 0px;
left: 0px;
width: 100%;
height: 100vh;
display: none;
background-color: #ddd;
opacity: 0.8;
}

.backlink {
color:black;
text-decoration:none;
font-size:large;
}

</style>""")
print("""
<script>
function typing() {
    document.getElementById('typingdiv').style.display = "flex"
    document.getElementById('graydiv').style.display = "block"
    document.body.style.cursor = 'wait'
}
function notyping() {
    document.getElementById('typingdiv').style.display = "none"
    document.getElementById('graydiv').style.display = "none"
    document.body.style.cursor = 'default'
}
</script>
""")
print("</head>\n")
print('<body onunload="notyping()">')

print("<!-- " + str(data) + "-->")

print('<div id="graydiv"></div>')

print('''
<div id="typingdiv">
<div id="horizontaldiv">
<img id="typingimg" src="robot.gif">
</div>
</div>
''')

# print HTML body
print(f"<h1>{page_title}</h1>")

print('<h1>!!!!! Currently disabled, use <a href="story_batch.py">batch generation</a> instead !!!!!</h1>')

# listing a scene with continuations
if 'key' in data:
    print(f"<p>Scene key: {data['key']}</p>")

    print("<div class='left'><pre id='prompt'>\n" + html.escape(data['prompt']) + "\n</pre>")
    print("<pre id='lines'>")
    num_lines = len(data['lines'])
    prefix = len(data['key']) - num_lines
    for i in range(num_lines):
        print('<a href="?id=' + data['key'][:prefix+i+1] + '" class="backlink">' + html.escape(data['lines'][i]) + '\n</a>', end='')
    print("</pre></div>")
    if 'cs_prompt' in data and 'cs_lines' in data:
        print("<div class='right'><pre id='prompt_tr'>\n" + html.escape(data['cs_prompt']) + "\n</pre>")
        print("<pre id='lines'>\n" + html.escape(data['cs_lines']) + "\n</pre></div>")

    history = []
    for cont in sorted(data['alts'].keys()):
        if data['alts'][cont] in history:

            print(f"<!--found a duplicate: {html.escape(data['alts'][cont])} -->")
            continue
        history.append(data['alts'][cont])

        print("<hr class='clear'>")
        # left
        print('<div class="left"><pre>\n' + html.escape(data['alts'][cont]) + "\n</pre></div>")
        # right
        print('<div class="right"><pre>\n' + (html.escape(data['cs_alts'][cont]) if 'cs_alts' in data else " ") + "\n</pre></div>")
        # link
        print('<p class="clear"><a href="?id=' + data['key'] + cont + '" onclick="typing();">Continue this dialogue</a>\n</p>')
    key = data['key'].split('-')
    if (len(key) >= 2 and len(key[1]) > 0):
        print('<hr>\n<a href="?id=' + data['key'][:-1] + '">Go back one step</a>')
    print('<hr>\n<a href="?">Back to main</a>')

# listing scenes
elif 'scenes' in data:
    for scene_key in sorted(data['scenes'].keys()):
        print("<hr>\nScene ID: " + scene_key + "\n<br>\n")
        print("<pre id='prompt'>" + html.escape(data['scenes'][scene_key]) + "</pre>")
        print('<a href="?id=' + scene_key + '-"  onclick="typing();">Explore this scene</a>')
    print('<hr>\n<a href="?add=1">Add a new scene</a>')

# showing errors
elif 'error' in data:
    print("<pre>\n" + data['error'] + "\n</pre>")
    print('<hr>\n<a href="?">Back to main</a>')

# adding new scene
elif 'add' in data:
    print('''
<form method="post" action="?">
    Scene ID: <input type="text" name="id"><br>
    Prompt text:<br>
    <textarea name="prompt" cols="50" rows="10"></textarea><br>
    <input type="submit" name="add" value="Submit">
</form>
          ''')

# footer
print("</body>")
print("</html>")
