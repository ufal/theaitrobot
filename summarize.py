#!/usr/bin/env python3

import json
from argparse import ArgumentParser

import pprint
import math
import spacy
import pytextrank
from collections import Counter
from random import choice

def scene2dic(prompt):
    """
    transforms scene string into prompt and list of dictionary utterances
    ["character":"Man","text":"blabla",]
    or in the presence of outline ["outline":"foobar killed roger rabbit"]
    """

    intro,*dial=prompt.split('\n')
    dial = list(filter(lambda x:x,dial))
    dial_seq = [ {'character':line.split(':')[0],"text":line.split(':')[1].strip()} 
                if ':' in line 
                else {"outline":line}
                for line in dial]
    
    return intro,dial_seq

def dic2prompt(dic):
    """
    transforms list of dictionary utterances into formated string
    """
    last_was_outline = False
    intro = dic[0]['text']
    formated_s = ''
    for u in dic[1:]:
        if 'character' in u:
            if last_was_outline:
                formated_s+= '\n\n'
                last_was_outline = False
            formated_s += u['character']+": "+u['text'] + '\n\n'
        else:
            formated_s += u['outline']
            last_was_outline = True


    return formated_s

def naive_sum(prompt,keep_n_last=2):
    """
    discards all but keep_n_last utterances keeping the seed prompt

    TODO: solve edge case when outline is in the [-2:] utterances
    """
    intro,d = scene2dic(prompt)
    rest = d[-keep_n_last:]
    string_to_append = "\n\n".join([x['character']+": "+x['text'] for x in rest if 'character' in x])
    return intro + '\n\n' + string_to_append

def filter_prompt(prompt,keep_last=3):
    """
    naively filters only utterances from the character that spoke last 
    """

    intro,dial_seq = scene2dic(prompt)
    last_to_speak = dial_seq[-1]['character']
    # remove lines spoken by someone else while preserving everything else
    filtered = list(filter(lambda x:x['character']==last_to_speak \
                                    if 'character' in x \
                                    else True), dial_seq[:-keep_last])
    new_seq = filtered + dial_seq[-keep_last:]
    
    return intro + "\n\n" + dic2prompt(new_seq)
    
    

def get_summary(lines, summary_len, limit_phrases=0):
    """Get the top summary_len lines from the play according to TextRank summarization.

       >> To download the model `python3 -m spacy download en_core_web_sm`
    """
    # Maybe think about removing the names of characters and pasting at the end?
    # lines = [":".join(l.split(':')[1:]) for l in lines]

    text = "\n".join(lines)
    nlp = spacy.load("en_core_web_sm")
    nlp.add_pipe("textrank")
    doc = nlp(text)

    # build a list of line boundaries, with a container for spacy phrases contained in each one
    line_bounds = []
    cur_start = 0
    cur_tok = 0
    bound = 0
    for line in lines:
        bound += len(line) + 1
        while cur_tok < len(doc) and doc[cur_tok].idx < bound:
            cur_tok += 1
        line_bounds.append([cur_start, cur_tok, set([])])
        cur_start = cur_tok

    # get TextRank scores for each line in the play, remember original order
    scores = [(idx, line, score) for idx, (line, score) in enumerate(line_scores(doc._.textrank, lines, line_bounds, limit_phrases))]
    # get the top summary_len scores, then sort according to original order in the play
    return sorted(sorted(scores, key=lambda item: item[2])[:summary_len])


def line_scores(textrank, lines, line_bounds, limit_phrases=0):
    """
    run extractive summarization, based on vector distance
    per line from the top-ranked phrases
    """
    unit_vector = []
    # iterate through the top-ranked phrases, added them to the
    # phrase vector for each line
    phrase_id = 0
    for p in textrank.doc._.phrases:
        unit_vector.append(p.rank)
        for chunk in p.chunks:
            for line_start, line_end, phrases_in_line in line_bounds:
                if  chunk.start >= line_start and chunk.start <= line_end:
                    phrases_in_line.add(phrase_id)
                    break
        phrase_id += 1
        if limit_phrases and phrase_id >= limit_phrases:
            break

    # construct a unit_vector for the top-ranked phrases, up to
    # the requested limit
    ranks_sum = sum(unit_vector)
    unit_vector = [rank / ranks_sum for rank in unit_vector]
    # iterate through each line, calculating its euclidean
    # distance from the unit vector

    line_ranks = []
    for line_start, line_end, phrases_in_line in line_bounds:
        sum_sq = 0.0
        for phrase_id in range(len(unit_vector)):
            # this was the problematic part.
            # it's more of a distance thank rank,
            # The less phrases are in a line, the larger the rank
            # so sorting in reverse gives the 'worst' lines

            if phrase_id not in phrases_in_line:
                sum_sq += unit_vector[phrase_id]**2.0
        line_ranks.append(math.sqrt(sum_sq))

    # return the distance
    return list(zip(lines, line_ranks))


def summarize_prompt(prompt, n_lines=3, limit_phrases=100):
    """get_summary that works on prompts"""

    line_list = prompt.split('\n')
    if n_lines > len(line_list):
        return prompt
    summary_lines = get_summary(line_list, n_lines, limit_phrases=limit_phrases)
    return "\n".join([s for (_, s, _) in summary_lines])


def summarize_dialogue(prompt, n_lines=3, limit_phrases=100,algorithm="textrank",keep_n_last=2):
    """get_summary that works on prompts
        TODO: FIX redundancy on join and then split
    """

    intro,d = scene2dic(prompt)
    d ,rest = d[:-keep_n_last], d[-keep_n_last:]
    string_to_summarize = "\n".join([ x['character']+": "+x['text'] \
                                if 'character' in x \
                                else x['outline'] for x in d] )
    line_list = string_to_summarize.split('\n')
    if n_lines >= len(line_list):
        return prompt

    summary_lines = get_summary(line_list, n_lines, limit_phrases=limit_phrases)
    return "\n\n".join([intro] + [s for (_, s, _) in summary_lines] \
                        + [x['character']+": "+x['text'] if 'character' in x else x['outline'] for x in rest] ) 




if __name__ == '__main__':
    ap = ArgumentParser()
    ap.add_argument('input_file', type=str)
    args = ap.parse_args()

    with open(args.input_file, 'r', encoding='UTF-8') as fh:
        data = json.load(fh)
    lines = ['%s: %s' % (item['character'], item['text']) for scene in data['scripts'][0]['acts'][0]['scenes'] for item in scene['contents'] if 'character' in item]
    summary = get_summary(lines, len(lines) // 10, limit_phrases=100)
    print(summary)
