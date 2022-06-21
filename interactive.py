#!/usr/bin/env python
# coding: utf-8

import gpt2
import torch

#tokenizer, model = gpt2.setup('distilgpt2')
tokenizer, model = gpt2.setup('gpt2-xl')


init_prompt = open('prompts/01.txt.ENG').read()


prompt = init_prompt


def gen_lines(prompt, num):
    gpt2.set_seed(123)
    context = tokenizer.encode(prompt) + [198]
    start_from = len(context)
    context = torch.tensor([context])
    context = context.to('cuda')

    output_sequences = gpt2.generate(model, tokenizer, context, start_from + 100, num)

    output_sequences = [tokenizer.decode(g.tolist()[start_from :], clean_up_tokenization_spaces=True)
                        for g in output_sequences]

    return ["\n".join(o.split('\n')[:1]) for o in output_sequences]

def write_expanded(filenum, key, data):
    for k, l in data:
        with open('interactive_data/' + filenum + '/' + key + k, 'w') as f:
            print(l, file=f)

story = dict()

def expand(filenum, key):
    prompt = [init_prompt]
    for i in range(1, len(key) + 1):
        prompt += [story[key[:i]]]
    prompt = '\n'.join(prompt)
    print('++++==============')
    print(prompt)
    lines = gen_lines(prompt, 5)
    write_expanded(filenum, key, zip('abcde', lines))
    for k, l in zip('abcde', lines):
        story[key + k] = l
