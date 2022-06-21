#!/usr/bin/env python3
# coding: utf-8

"""
Kdybyste tohle chtěli pouštět:
 -  -h vypisuje parametry
 -  virtuální environment s nainstalovaným torchem je gpt2/venv-gpt-2
 -  pro nastavení CUDAy na clusteru sórsujte: . gpt2/set_cuda_10_1
 -  pokud nechcete, aby se vám do houmu stahovalo 7 GB modelu, symlinkujte si z ~/.cache/torch složku /net/data
ELITR/gpt/gpt-2/transformers
"""

import torch
from transformers import GPT2Tokenizer, GPT2LMHeadModel
import numpy as np
import re

import logging
logging.basicConfig(level=logging.INFO)

def set_seed(seed):
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

def setup(model_name):
    tokenizer = GPT2Tokenizer.from_pretrained(model_name)

    # Load pre-trained model (weights)
    model = GPT2LMHeadModel.from_pretrained(model_name)

    # Set the model in evaluation mode to deactivate the DropOut modules
    # This is IMPORTANT to have reproducible results during evaluation!
    model.eval()

    # If you have a GPU, put everything on cuda
    model.to('cuda')

    return tokenizer, model

def generate_limit_chars(prompt, length, char_trie):
    generated = tokenizer.encode(prompt)
    context = torch.tensor([generated])
    context = context.to('cuda')
    past = None
    next_allowed = None

    for i in range(length):
        output, past = model(context, past=past)
        output = output[..., -1, :]

        if next_allowed is not None:
            # Mask out everything but possible character names
            new_output = torch.zeros_like(output)
            new_output = new_output.fill_(-float('inf'))
            for i in next_allowed:
                new_output[i] = output[i]
            output = new_output

            token = torch.argmax(output)

            child = char_trie.get_successor(token)
            if child is not None and child.value != 25:
                next_allowed = char_trie.get_children_of_current()
            else:
                char_trie.reset_current()
                next_allowed = None
        else:
            token = torch.argmax(output)
            if token == char_trie.newline:
                next_allowed = char_trie.get_children_of_current()

        generated += [token.tolist()]
        context = token.unsqueeze(0)

    sequence = tokenizer.decode(generated)

    return(sequence)

class trie_node():
    def __init__(self, value = None):
        self.value = value
        self.children = set()

    def add_child(self, value):
        child = self.get_child(value)
        if child is not None:
            return child
        else:
            child = trie_node(value)
            self.children.add(child)
            return child

    def get_child(self, value):
        for child in self.children:
            if child.value == value:
                return child
        return None

    def get_children_values(self):
        values = []
        for child in self.children:
            values.append(child.value)
        return values

    def print_node(self, _prefix="", _last=True):
        print(_prefix, "`- " if _last else "|- ", self.value, sep="")
        children = self.get_children_values()
        _prefix += "   " if _last else "|  "
        child_count = len(children)
        for i, child in enumerate(children):
            _last = i == (child_count - 1)
            self.get_child(child).print_node(_prefix, _last)


class trie():
    # List containing lists containing encoded characters
    def __init__(self, char_list):
        self.newline = 198  #198 is an encoded newline
        self.root = trie_node(self.newline)

        for character in char_list:
            self.current = self.root
            for subword in character:
                self.add_child_to_current(subword)

        self.current = self.root

    def reset_current(self):
        self.current = self.root

    def add_child_to_current(self, value):
        self.current = self.current.add_child(value)

    def get_successor(self, value):
        child = self.current.get_child(value)
        if child is not None:
            self.current = child
        else:
            self.current = self.root
        return child

    def get_children_of_current(self):
        return self.current.get_children_values()

    def print_trie(self):
        self.root.print_node()



if __name__ == "__main__":

    import sys
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument("--length", type=int, default=200)
    parser.add_argument("--model", type=str, default='gpt2')
    parser.add_argument("--prompts_dir", type=str, default=None)
    parser.add_argument("--out_dir", type=str, default=None)
    parser.add_argument("--sequences", type=int, default=1)
    parser.add_argument("--rpenalty", type=float, default=1.0)
    parser.add_argument("--topp", type=float, default=0.9)
    parser.add_argument("--temp", type=float, default=1.0)

    args = parser.parse_args()

    if args.prompts_dir is None:
        prompts = [sys.stdin.read()]
        files = [sys.stdout]
    else:
        import os
        infiles = os.listdir(args.prompts_dir)
        prompts = [open(args.prompts_dir + '/' + f).read() for f in infiles]
        if args.out_dir is None:
            files = [sys.stdout] * len(prompts)
        else:
            files = [open(args.out_dir + '/' + f, 'w') for f in infiles]

    tokenizer, model = setup(args.model)

    for prompt, out in zip(prompts, files):

        # Create a trie of characters
        characters = set()
        encoded_characters = []
        for line in prompt.split('\n'):
            # filter out scenic remarks
            if "[" in line or "]" in line or "/" in line:
                continue
            characters.add(re.sub(":.*", ":", line))  # Keeping the colon to make sure nothing will be appended to the character name

        for character in characters:
            encoded_characters.append(tokenizer.encode(character))

        char_trie = trie(encoded_characters)

        # Generate
        context = tokenizer.encode(prompt)
        context = [tokenizer.eos_token_id] + context
        start_from = len(context)
        context = torch.tensor([context])
        context = context.to('cuda')

        output_sequences = generate_limit_chars(prompt, args.length, char_trie)
        print(output_sequences, file=out)

        if len(files) > 1:
            out.close()
