#!/usr/bin/env python
# coding: utf-8

"""
Kdybyste tohle chtěli pouštět:
 - pre guided_generate zatial treba nainstalovat nltk
 - bolo to spúštané na CPU tak gpu-related kod je zakomentovaný
 - funguje len pre default argument sequences == 1

 -  -h vypisuje parametry
 -  virtuální environment s nainstalovaným torchem je gpt2/venv-gpt-2
 -  pro nastavení CUDAy na clusteru sórsujte: . gpt2/set_cuda_10_1
 -  pokud nechcete, aby se vám do houmu stahovalo 7 GB modelu, symlinkujte si z ~/.cache/torch složku /net/data/ELITR/gpt/gpt-2/transformers
"""

import torch
from transformers import GPT2Tokenizer, GPT2LMHeadModel
import numpy as np

import logging
logging.basicConfig(level=logging.INFO)

def set_seed(seed):
    np.random.seed(seed)
    torch.manual_seed(seed)
    # torch.cuda.manual_seed_all(seed)

def setup(model_name):
    tokenizer = GPT2Tokenizer.from_pretrained(model_name)

    # Load pre-trained model (weights)
    model = GPT2LMHeadModel.from_pretrained(model_name)

    # Set the model in evaluation mode to deactivate the DropOut modules
    # This is IMPORTANT to have reproducible results during evaluation!
    model.eval()

    # If you have a GPU, put everything on cuda
    # model.to('cuda')

    return tokenizer, model

# Predict all tokens
#with torch.no_grad():
#    outputs = model(tokens_tensor)
#    predictions = outputs[0]

# get the predicted next sub-word (in our case, the word 'man')
#predicted_index = torch.argmax(predictions[0, -1, :]).item()
#predicted_text = tokenizer.decode(indexed_tokens + [predicted_index])
#assert predicted_text == 'Who was Jim Henson? Jim Henson was a man'

def greedy(prompt, length):
    generated = tokenizer.encode(promp)
    context = torch.tensor([generated])
    context = context.to('cuda')
    past = None

    for i in range(length):
        output, past = model(context, past=past)
        token = torch.argmax(output[..., -1, :])

        generated += [token.tolist()]
        context = token.unsqueeze(0)

    sequence = tokenizer.decode(generated)

    return(sequence)

def generate(model, tokenizer, context, max_len, sequences, greedy=False, beam=1, r_penalty=1.0, top_p=0.9, temp=1.0):

    output_sequences = model.generate(
           input_ids=context,
           max_length=max_len,
           temperature=temp,
           top_k=50,
           top_p=top_p,
           repetition_penalty=r_penalty,
           do_sample= (not greedy) or beam > 1,
           num_beams=beam,
           num_return_sequences=sequences,
       )

    if len(output_sequences.shape) > 2:
        output_sequences.squeeze_()
    return output_sequences






def guided_generate(model, tokenizer, context, max_len, sequences, greedy=False, beam=1, r_penalty=1.0, top_p=0.9, temp=1.0):
    ############## Utilites

    def show(tensor):
        """ prints tensor to stdout in readable form """
        print(tokenizer.decode(tensor.squeeze(), clean_up_tokenization_spaces=True))


    # adds a character into context tensor to speak next
    def add_random_character(con,char_set):
        """ con is pytorch tensor of gpt-context """
        con2 = con.squeeze()
        con2 = con2.tolist() + tokenizer.encode('\n' + random.sample(char_set,1)[0]+': ')
        return torch.tensor([con2])



    # assumes prompts to be formated --> JOHN: Lorem ipsum\n
    def extract_characters(id_seq):
        """ Returns a set of string corresponding to characters from id_seq tensor """
        string = tokenizer.decode(id_seq.squeeze()[1:], clean_up_tokenization_spaces=True)
        characters = set([x.split(':')[0] for x in string.split('\n') if x.find(':')!=-1 ])
        return characters


    # TODO: check if the string is a reply or a scenic remark?
    def ok(string):
        return True

    ##############

    from nltk import tokenize
    import random
    import re




    REPLY_MAX_LEN=50
    NUM_REPLIES= max_len // REPLY_MAX_LEN
    FIRST=True
    random.seed(123)

    characters=extract_characters(context)
    context2=context

    for y in range(NUM_REPLIES):
        i=0
        FIRST=True
        while FIRST or not ok(reply):
            FIRST=False
            i+=1


            context2 = add_random_character(context2,characters)

            context_len = context2.shape[1]

            # crashes when context is too long
            # should be remade so context starts shrinking from the start
            if context_len + REPLY_MAX_LEN > 1023:
                return [output_sequences]

            output_sequences = model.generate(
                   input_ids=context2,
                   max_length=context_len + REPLY_MAX_LEN,
                   temperature=temp,
                   top_k=50,
                   top_p=top_p,
                   repetition_penalty=r_penalty,
                   do_sample= (not greedy) or beam > 1,
                   num_beams=beam,
                   num_return_sequences=sequences)
            if len(output_sequences.shape) > 2:
                output_sequences.squeeze_()


            # cut out sentence_reply from the generated sequence with nltk sentence tokenizer.
            gen_seq = output_sequences.squeeze_().tolist()[context_len :]
            gen_str = tokenizer.decode(gen_seq,clean_up_tokenization_spaces=True)


            # remove nested scenic remarks
            re.sub(r"[\(\[\{].*?[\)\]\}]", '', gen_str)
            re.sub(r"[\(\[\{].*?[\)\]\}]", '', gen_str)
            re.sub(r"[\(\[\{].*?[\)\]\}]", '', gen_str)

            # first sentence is the reply
            reply = tokenize.sent_tokenize(gen_str)[0]
            if ok(reply):
                encoded_reply = tokenizer.encode(reply)
                context_tmp=torch.tensor([context2.squeeze().tolist() +encoded_reply])
                context_len = context_tmp.shape[1]
                context2=context_tmp
            else:
                pass
                # change seed?



    if len(output_sequences.shape) > 2:
        output_sequences.squeeze_()
    return [output_sequences]


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
        context = tokenizer.encode(prompt)
        context = [tokenizer.eos_token_id] + context
        start_from = len(context)
        context = torch.tensor([context])

        # context = context.to('cuda')

        output_sequences = guided_generate(model, tokenizer, context, \
                start_from + args.length, 1, \
                r_penalty=args.rpenalty, top_p=args.topp, \
                )
        generated_sequences = []

        for generated_sequence_idx, generated_sequence in enumerate(output_sequences):
            print("=== GENERATED SEQUENCE {} ===".format(generated_sequence_idx + 1), file=out)
            generated_sequence = generated_sequence.tolist()[start_from :]

            # Decode text
            text = tokenizer.decode(generated_sequence, clean_up_tokenization_spaces=True)
            print(text, file=out)
        if len(files) > 1:
            out.close()
