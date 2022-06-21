#!/usr/bin/env python
import re
import sys

from transformers import RobertaTokenizer, RobertaForSequenceClassification, AutoModelForSequenceClassification
import torch.nn.functional as F
import torch
#from metrics import metrics


class NLI:
    def __init__(self):
        self.tokenizer = RobertaTokenizer.from_pretrained('roberta-large-mnli')
        self.model = AutoModelForSequenceClassification.from_pretrained('roberta-large-mnli')
        self.label_map = {'contradiction': 0, 'neutral': 1, 'entailment': 2}
        self.max_len = 512
        self.replace_rule = re.compile(r' ?[^ ]+ ')
        seed = 42
        torch.manual_seed(seed)

    def get_single_nli_score(self, previous, utterance):
        prompt = previous + '</s></s>' + utterance
        previous += ' ' + utterance
        ids = self.tokenizer(prompt, return_tensors="pt")#[-self.max_len:]
        if len(ids['input_ids'][0] > self.max_len):
            input_ids = ids['input_ids'][0][-self.max_len:]
            input_ids = torch.unsqueeze(input_ids, 0)
            attention_mask = ids['attention_mask'][0][-self.max_len:]
            attention_mask = torch.unsqueeze(attention_mask, 0)
        output = self.model(input_ids=input_ids, attention_mask=attention_mask, return_dict=True)
        #output = self.model(**ids, return_dict=True)
        output = F.softmax(output.logits, dim=1)
        # We want to encourage neutrality
        result = output[0][self.label_map['neutral']]
        return result

    
    def get_nli_score(self, utterances):
        if len(utterances) < 2:
            print('Only one utterance!')
            print(utterances)
            return 0.3 # Hopefully this doesn't happen too often
        previous = ''
        score = 0.0
        for utterance in utterances:
            if previous == '':
                previous = utterance
            else:
                result = self.get_single_nli_score(previous, utterance) 
                score += result
                #print(f'{prompt}\t{result}')
        return score/(len(utterances) - 1) # We want to average by the number of comparisons made, not the number of utterances

def process_dialog_data():
    input_file = sys.argv[1]
    nli = NLI()
    outfile = open('out_nli_' + input_file, 'w')
    outfile.write('Seed\tNLI-score\tPerplexity\t1gramVocabSize\t2gramVocabSize\tWordsTotal\tNumReplies\n')
    outfile.close()
    with open (input_file, 'r') as infile:
        curr_seed = 0
        curr_dialog = dict()
        all_utterances = []
        num_replies = 0
        for line in infile:
            # Skip empty lines
            if len(line) < 1:
                continue
            # Read the seed
            elif line.startswith('Seed:'):
                curr_seed = int(line.replace('Seed: ', '').strip())
            # Scene separator, evaluate
            elif line.startswith('##'):
                print(f'Evaluating dialog with seed {curr_seed}.')
                sum_per_dialog = 0.0
                # Compute consistency per character
                for char in curr_dialog.keys():
                    score = nli.get_nli_score(curr_dialog[char])
                    sum_per_dialog += score
                    #print(f'Consistency of character {char}: {score:5f}')
                # Compute dialog average
                avg = sum_per_dialog / len(curr_dialog.keys())
                """perplex, unigram, bigram = metrics(all_utterances)
                print(f'Average consistency per dialog: {avg:5f}')
                outfile = open('out_nli' + input_file, 'a')
                outfile.write(f'{curr_seed}\t{avg:5f}\t{perplex:5f}\t{len(unigram.keys())}\t{len(bigram.keys())}\t{len(all_utterances)}\t{num_replies}\n')
                outfile.close() """

                # Clear the current dialog
                curr_dialog = dict()
                all_utterances = []
                num_replies = 0
            # Dialog line, extract the character and the utterance
            elif line.startswith('From'):
                char_name = re.sub(r'From ([^ ]+) to.*',r'\1', line).strip()
                utterance = re.sub(r'From[^:]+:', '', line).replace('"', '')
                if char_name not in curr_dialog:
                    curr_dialog[char_name] = []
                curr_dialog[char_name].append(utterance)
                all_utterances.extend(utterance.split(' '))
                num_replies += 1

    outfile.close()


if __name__ == "__main__":
    #process_dialog_data()
    nli = NLI()
    previous = "Late one night, Albus Dumbledore and Minerva McGonagall, professors at Hogwarts School of Witchcraft and Wizardry, along with groundskeeper Rubeus Hagrid, deliver an orphaned infant named Harry Potter to his aunt and uncle, Petunia and Vernon Dursley, his only living relatives. Just before Harry's eleventh birthday, owls begin delivering letters addressed to him. When the abusive Dursleys refuse to allow Harry to open any, Hagrid arrives to personally deliver Harry's letter. Hagrid also reveals that Harry's parents, James and Lily Potter, were killed by dark wizard Lord Voldemort. The killing curse that Voldemort had cast rebounded, destroying Voldemort's body and giving Harry his lightning-bolt scar. Hagrid then takes Harry to Diagon Alley for school supplies and gives him a pet owl he names Hedwig. Harry buys a wand that is connected to the dark wizard Lord Voldemort's own wand. At King's Cross station, Harry boards the Hogwarts Express train. He meets Ron Weasley and Hermione Granger, a Muggle-born witch. Harry also encounters Draco Malfoy who is from a wealthy, pure-blood wizard family. The two immediately form a rivalry. At Hogwarts, students assemble in the Great Hall where the Sorting Hat sorts the first-years among four houses: Gryffindor, Hufflepuff, Ravenclaw, and Slytherin. Harry is placed into Gryffindor alongside Ron and Hermione. Draco is sorted into Slytherin, a house noted for dark wizards. As Harry studies magic, he learns more about his parents and Lord Voldemort. Harry's natural talent for broomstick flying gets him recruited as the youngest-ever Seeker for Gryffindor's Quidditch team. While returning to the Gryffindor common room, the staircases change paths, leading Harry, Ron, and Hermione to a restricted floor. There they discover a giant three-headed dog named Fluffy. Later, Ron insults Hermione after she embarrasses him in Charms class. Upset, Hermione locks herself in the girls' bathroom. A giant marauding troll enters it, but Harry and Ron save Hermione, and the three become friends. The trio discover that Fluffy is guarding the philosopher's stone, a magical object that can turn metal into gold and produce an immortality elixir. Harry suspects that Potions teacher and head of Slytherin House, Severus Snape, wants the stone to return Voldemort to physical form. When Hagrid accidentally reveals that music puts Fluffy asleep, Harry, Ron, and Hermione decide to find the stone before Snape. Fluffy is already asleep, but the trio face other barriers, including a deadly plant called Devil's Snare, a room filled with aggressive flying keys, and a giant chess game that knocks out Ron. After overcoming the barriers, Harry discovers that Defence Against the Dark Arts teacher Quirinus Quirrell wants the stone; Snape had figured it out and had been protecting Harry. Quirrell removes his turban and reveals a weakened Voldemort living on the back of his head. Dumbledore's protective enchantment places the stone in Harry's possession. Voldemort attempts to bargain the stone from Harry in exchange for resurrecting his parents, but Harry refuses. Quirrell attempts to kill Harry. When Harry touches Quirrell's skin, it burns Quirrell, reducing him to ashes. Voldemort's soul rises from the pile and escapes, knocking out Harry as it passes through him."
    utterance = "Harry recovers in the school infirmary."
    print(nli.get_single_nli_score(previous, utterance))
