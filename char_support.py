#!/usr/bin/env python
import re
import torch
from torch.nn import functional as F


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

    def print_node(self, tokenizer, _prefix="", _last=True):
        print(_prefix, "`- " if _last else "|- ", tokenizer.decode([self.value]), sep="")
        children = self.get_children_values()
        _prefix += "   " if _last else "|  "
        child_count = len(children)
        for i, child in enumerate(children):
            _last = i == (child_count - 1)
            self.get_child(child).print_node(tokenizer, _prefix, _last)


class trie():
    # List containing lists containing encoded characters
    def __init__(self, char_list):
        self.newline = 198  #198 is an encoded newline
        self.colon = 25
        self.root = trie_node(self.newline)

        for character in char_list:
            self.current = self.root
            for subword in character:
                self.add_child_to_current(subword)
            self.add_child_to_current(self.colon)

        self.current = self.root
        self.next_allowed = self.get_children_of_current()
        self.character_history = []
        self.current_character = []
        self.char_list = char_list

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

    def print_trie(self, tokenizer):
        self.root.print_node(tokenizer)

    def prefer_char_probs(self, probs, history_coefficient = 2):
        probs = probs[..., -1, :]
        if (torch.argmax(probs) == self.newline):
            self.next_allowed = self.get_children_of_current()
            return F.softmax(torch.unsqueeze(probs, 0))

        # TODO: plug in history
        # Either softmax everything twice, or use signum for multiplication/division?
        if self.next_allowed is not None:
            # Mask out everything but possible character names
            new_output = torch.zeros_like(probs)
            probs = F.softmax(probs)
            new_output = new_output.fill_(0)
            # Pre kazdu z povolenych postav zvyhodnit jej pravdepodobnosť podľa jej posledného výskytu
            for i in self.next_allowed:
                last_occurrence = self.find_last_occurrence(i)
                new_output[i] = probs[i] * history_coefficient ** (10 - last_occurrence)
            probs = new_output
        
        return(torch.unsqueeze(probs, 0))

    def find_last_occurrence(self, subword_id):
        last_occurrence = -1
        self.current_character.append(subword_id)
        for c, character in enumerate(self.character_history):
            inc = True
            # Check the sublist to make sure it is the right character path in trie
            for j in range(len(self.current_character)):
                if character[j] != self.current_character[j]:
                    inc = False
                    break
            if inc:
                last_occurrence = c
        self.current_character.pop()
        return last_occurrence

    # Returns true at a newline, signal to classify the
    def set_next_allowed(self, token):
        if token == self.newline:
            self.next_allowed = self.get_children_of_current()
            return True
        elif self.next_allowed is None:
            return False
        else:
            child = self.get_successor(token)
            self.current_character.extend(token)
            if child is not None and child.value != self.colon:
                self.next_allowed = self.get_children_of_current()
            else:
                self.reset_current()
                self.next_allowed = None
                self.character_history.append(self.current_character)
                self.current_character = []
                self.character_history = self.character_history[-10:]
        return False

def extract_character_names(prompt):
    characters = set()
    for line in prompt.split('\n'):
        # filter out scenic remarks
        if "[" in line or "]" in line or "/" in line:
            continue
        if ':' not in line:
            continue
        characters.add(re.sub(":.*", "", line))
    return characters

def build_trie(tokenizer, characters):
    # Create a trie of characters
    encoded_characters = []

    if len(characters) == 0:
        return None

    for character in characters:
        encoded_characters.append(tokenizer.encode(character))

    return trie(encoded_characters)
