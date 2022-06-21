
import json
import traceback
import sys
from api_token import get_token
from keyops import compress_key
import random


def load_config(filename):
    SERVER_ADDR = 'http://localhost:8456'
    API_ADDR = 'http://ufallab.ms.mff.cuni.cz:8457'
    try:
        with open(filename) as configfile:
            config = json.load(configfile)
            SERVER_ADDR = config['SERVER_ADDR']
            if isinstance(SERVER_ADDR, list):
                SERVER_ADDR = random.choice(SERVER_ADDR)
            API_ADDR = config.get('API_ADDR', API_ADDR)
    except Exception:
        pass  # keep the default
    return SERVER_ADDR, API_ADDR


def print_html_head(page_title, username, data, api_addr):
    # print HTML header
    print('<!DOCTYPE html>\n<html lang="en">')

    print('<head>\n<meta charset="utf-8">')
    print(f"<title>{page_title}</title>")

    print("""<style>

    pre {
    padding: 0px 1em 0px 1em;
    font-size: large;
    white-space: pre-wrap;
    margin-bottom: 0px;
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

    #outline{
    background-color: #eef;
    }

    #outline_tr {
    background-color: #ddf;
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

    .lines {
    margin-top: 1ex;
    }

    .lines:hover {
    background-color: #eef;
    }

    .theend {
    font-weight: bold;
    margin-top: 1em;
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

    .backlink, .discardlink, .newlink, .human_link, .cutlink, .cutbacklink, .addlink {
    font-weight: bold;
    text-decoration:none;
    font-size:large;
    }

    a.star {
    text-decoration:none;
    color:gray;
    }

    .human_link, .addlink {
    color:green;
    }

    .backlink, .newlink {
    color:blue;
    }

    .backlink.human, .rated a.star {
    color:green;
    }

    .discardlink, .failed a.star {
    color:red;
    }

    .cutlink {
    color:blue;
    font-size: large;
    }

    .cutbacklink {
    color:red;
    }

    .in-progress a.star {
    color: yellow;
    }

    .human_input_form {
    display: none;
    padding: 0;
    white-space: normal;
    background: #cfc;
    font-family: serif;
    font-size: medium;
    }

    .human_input {
    background: #eee;
    white-space: pre-wrap;
    }

    .synopsis2script {
    padding: 1em 1em 1em 1em;
    }

    .command {
        font-family: monospace;
        color: green;
        padding: 0.5ex 1em 0px 1em;
    }

    .command .button {
        cursor: pointer;
    }

    .command input {
        border: 0;
        font-family: monospace;
        color: green;
        margin-left: -0.3ex;
    }

    .command:hover, .command:hover input {
        background: #cfc;
    }

    .command:hover .button {
        background: #7f7;
    }
    </style>""")

    print("<script type=\"text/javascript\">\n\n")
    try:
        print("var data = " + json.dumps(data, indent=4, ensure_ascii=False) + ";\n")
    except Exception:
        print(traceback.format_exc())
        sys.exit()
    print(f"var username = '{username}';\n")
    print(f"var token = '" + get_token(username) + "';\n")
    print(f"var ajaxURL = '{api_addr}';\n")
    print("""

    var humanInputPos = -1;

    // shorthand for the most frequent function
    function getEl(id) { return document.getElementById(id) };

    // https://plainjs.com/javascript/ajax/send-ajax-get-and-post-requests-47/
    function post_ajax(data, callback) {

        var xhr = window.XMLHttpRequest ? new XMLHttpRequest() : new ActiveXObject("Microsoft.XMLHTTP");
        xhr.open('POST', ajaxURL);
        xhr.onreadystatechange = function() {
            if (xhr.readyState > 3){
                callback(xhr.status);
            }
        };
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.setRequestHeader('Content-Type', 'application/json; charset=utf-8');
        xhr.send(JSON.stringify(data));
        return xhr;
    }

    function typing() {
        getEl('typingdiv').style.display = "flex"
        getEl('graydiv').style.display = "block"
        document.body.style.cursor = 'wait'
    }

    function notyping() {
        getEl('typingdiv').style.display = "none"
        getEl('graydiv').style.display = "none"
        document.body.style.cursor = 'default'
    }

    function toggle_human_input(key){
        var form = getEl('human_input_form_' + key);
        if (form.style.display == "block"){
            form.style.display = "none";
        }
        else {
            form.style.display = "block";
        }
    }

    function cancel_human_input_func(){
        getEl('human_input_form').style.display = "none";
        humanInputPos = -1;
    }

    function set_rating(elem, key, rating){

        var html = '';
        for (var i = 1; i <= 5; ++i){
            html += '<a href="#" class="star star-' + i + '" onclick="set_rating(this.parentElement, \\\'' + key + '\\\', ' + i + '); return false;">';
            html += (i <= rating ? '&#9733;' : '&#9734;' ) + '</a>';
        }

        elem.innerHTML = html;

        // rating = 0 means "reset & not call anything"
        // rating in <1,5> will actually try to set the rating
        if (rating > 0){
            elem.classList.add('in-progress');
            elem.classList.remove('rated', 'failed');
            post_ajax(
                {'username': username,
                'key': key,
                'rating': rating,
                'token': token},
                function(status){ update_rating(elem, key, rating, status); }
            );
        }
    }

    function update_rating(elem, key, rating, status){

        elem.classList.remove('in-progress');

        if (status == 200){
            elem.classList.add('rated');
        }
        else {
            set_rating(elem, key, 0);
            elem.classList.add('failed');
        }
    }
    """)
    if 'key' in data:
        print(f"history.replaceState({{}}, '{page_title}', '?id={compress_key(data['key'])}')")

    print("\n\n</script>")
    print("</head>\n")


def print_rating_links(key, rating):
    rating = rating or 0
    html_class = 'rated' if rating else ''
    html = '<span class="stars {html_class}">'
    for i in range(1, 6):
        html += f'<a href="#" class="star star-{i} {html_class}" onclick="set_rating(this.parentElement, \'{key}\', {i}); return false;">'
        html += '&#9733;' if i <= rating else '&#9734;'
        html += '</a>'
    html += '</span>'
    print('<p class="clear">Rate: ' + html + '</p>')


def print_recent_list(username, data):
    """List recently generated stuff."""

    print('<a href="?">Back to main</a>&nbsp;')
    # we're listing current user's history -> link to global history
    if 'username' in data:
        print('<a href="?recent=0">All recently generated</a>&nbsp;')
    # we're listing global history & username is set -> link to current user's history
    elif username:
        print('<a href="?my_recent=0">My recently generated</a>&nbsp;')
    if username:
        print(f'Username: {username} &nbsp;')
    print('<hr>\n<table><tr><th>Date &amp; time</th><th>User</th><th>Rating</th><th>Generated key</th></tr>\n')

    for acc_key in data['recent']:
        print('<tr><td>' + acc_key['timestamp'] + '</td>'
              + '<td>' + (acc_key.get('username', '') or '') + '</td>'
              + '<td>' + ('&#9733;' * (acc_key.get('rating', 0) or 0)) + '</td>'
              + '<td><a href="?id=' + compress_key(acc_key['key']) + '">' + compress_key(acc_key['key'], trunc=True) + '</a></td></tr>\n')
    print('</table>\n')


def human_input_link(key):
    return f'''<a href="#" class="human_link" onclick="toggle_human_input('{key}'); return false;" title="Add manual input">&#9660;</a>'''


def human_input_form(key):
    # form for human inputs (hidden initially)
    # NOTE: always preserve preceding space, AND assume it is '\n'
    return f'''<form method="post" class="human_input_form" id="human_input_form_{key}" action="?">
        <input type="hidden" name="id" value="{key}">
        <input type="hidden" name="pre_space" value="\n">
        <input type="hidden" name="use_pre_space" value="1">
        <input type="hidden" name="input_type" value="human">
        Input:<br><textarea name="human_input" id="human_input" rows="2" cols="60"></textarea><br>
        <input type="button" name="cancel_human_input" value="Cancel" onclick="toggle_human_input('{key}');">
        <input type="submit" name="confirm_human_input" value="Confirm" onclick="typing();">
    </form>'''
