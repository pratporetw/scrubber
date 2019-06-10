from itertools import groupby
from nltk.tag import pos_tag
import argparse
import fileinput
import os
import re


parser = argparse.ArgumentParser(description='Scrubber script. Masks PIIs with {{TAG}}s')
parser.add_argument("--inpf", type=str, help="Absolute file path for input file.")
parser.add_argument("--outf", type=str, help="Absolute file path for output csv.")
parser.add_argument("--dryrun", type=bool, default=False, help="Whether to run in dry mode")
args = parser.parse_args()

class Scrubber():
    CLEANER_TAGS = ["{{MENTION}}", "{{ID}}", "{{NUMBER}}", "{{EMAIL}}", "{{DOMAIN_NAME}}", "{{URL}}",
                    "{{NAME}}", "{{NON_ENGLISH}}", "{{IP}}", "{{DATE}}", "{{TIME}}", "{{SALUTATION}}"]
    HI_PATTERN = r'hel{1,4}o|hi|hey|dear'
    GREETINGS_PATTERN = r'^((?:%s)[,\.]|(?:%s) (\w+[,\. ]?){1,3})' % (HI_PATTERN, HI_PATTERN)

    mentions_re = re.compile(r'@[a-zA-Z0-9_]+')
    ids_re = re.compile(r'[0-9][a-zA-Z0-9-_]*[a-zA-Z]+[a-zA-Z0-9]*'
                        r'|[a-zA-Z][a-zA-Z0-9-_]*[0-9]+[a-zA-Z0-9]*')
    explicit_ids_re = re.compile(r'(\bid\s?(?:-|=|:)\s*)(\w+)', re.I)
    numbers_re = re.compile(r'\+?\d+[\d -\.]{2,}\d+')
    emails_re = re.compile(r'\b[a-zA-Z0-9_\.]+@[a-zA-Z0-9.]+\b')
    domains_re = re.compile(r'\b([a-zA-Z0-9][a-zA-Z0-9-]{,61}[a-zA-Z0-9]\.)+[a-zA-Z]{2,5}\b', re.I)
    urls_re = re.compile(r'\b(?:[a-z0-9]{2,5}://|www\.)[^\s]*\b')
    greetings_re = re.compile(GREETINGS_PATTERN, re.I)
    salutations_re = re.compile(r'(?:thank(?:s|ing)?( ?you)?|(best )?regards|sincerely|yours \w{4,10}ly).{,50}$', re.I)
    times_re = re.compile(r'\d{1,2}[:\.]\d{1,2}([:\.]\d{1,2})?(?: ?am| ?pm)?', re.I)
    dates_re = re.compile(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}')
    ips_re = re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
    split_re = re.compile(r'\s|=|:|\*|\'|\"|\.|\|')
    names_re = re.compile(r'(name\s?(?:-|=|:)\s*)(\w+)', re.I)

    clean_methods = ["clean_non_english", "clean_salutations", "clean_emails", "clean_mentions",
                     "clean_ips", "clean_dates", "clean_times", "clean_numbers", "clean_ids",
                     "clean_urls", "clean_domain", "clean_names_regex", "clean_names"]

    @staticmethod
    def dry_clean(text):
        # Doesn't replace text with tags. Just return positions for matches.
        old_text = text
        all_annots = []
        old_len = len(text)
        for method in Scrubber.clean_methods:
            annots = getattr(Scrubber, method)(text, dry=True)
            all_annots.extend(annots)
            for start, end in annots:
                text = text[:start] + ("^" * (end - start)) + text[end:]
        assert old_len == len(text)
        all_annots.sort(key=lambda k: k[0])
        # Converting to list of list from list of tuples.
        all_annots = [list(tup) for tup in all_annots]
        return old_text, all_annots

    @staticmethod
    def clean(text):
        # Replaces text with respective {{TAG}} for method.
        text = text.strip()
        for method in Scrubber.clean_methods:
            text = getattr(Scrubber, method)(text)
        text = Scrubber.clean_repeated_tags(text)
        return text

    @staticmethod
    def clean_repeated_tags(text):
        for tag in Scrubber.CLEANER_TAGS:
            text = re.sub(r'(?:%s\s*)*%s' % (tag, tag), tag, text)
        return text

    @staticmethod
    def clean_mentions(text, dry=False):
        if dry:
            return [annot.span() for annot in Scrubber.mentions_re.finditer(text)]
        return Scrubber.mentions_re.sub("{{MENTION}}", text)

    @staticmethod
    def clean_ids(text, dry=False):
        if dry:
            annots = [annot.span() for annot in Scrubber.ids_re.finditer(text)]
            for start, end in annots:
                text = text[:start] + ("^" * (end - start)) + text[end:]
            annots.extend([annot.span(2) for annot in Scrubber.explicit_ids_re.finditer(text)])
            return annots
        text = Scrubber.ids_re.sub("{{ID}}", text)
        return Scrubber.explicit_ids_re.sub(r"\1{{ID}}", text)

    @staticmethod
    def clean_numbers(text, dry=False):
        if dry:
            return [annot.span() for annot in Scrubber.numbers_re.finditer(text)]
        return Scrubber.numbers_re.sub("{{NUMBER}}", text)

    @staticmethod
    def clean_emails(text, dry=False):
        if dry:
            return [annot.span() for annot in Scrubber.emails_re.finditer(text)]
        return Scrubber.emails_re.sub("{{EMAIL}}", text)

    @staticmethod
    def clean_domain(text, dry=False):
        if dry:
            return [annot.span() for annot in Scrubber.domains_re.finditer(text)]
        return Scrubber.domains_re.sub("{{DOMAIN_NAME}}", text)

    @staticmethod
    def clean_urls(text, dry=False):
        if dry:
            return [annot.span() for annot in Scrubber.urls_re.finditer(text)]
        return Scrubber.urls_re.sub("{{URL}}", text)

    @staticmethod
    def clean_names(text, dry=False):
        words = Scrubber.split_re.split(text)
        tags = pos_tag([word for word in words if word])
        annots = []
        index_of_words_occurred = {}
        for pos, (word, tag) in enumerate(tags):
            index_of_word = words.index(word, index_of_words_occurred.get(word, 0))
            index_of_words_occurred[word] = index_of_word + 1
            empty_words_delta = len([w for w in words[:index_of_word] if w == ''])
            start = len(" ".join(entry[0] for entry in tags[:pos])) + \
                (0 if pos == 0 else 1) + \
                empty_words_delta
            end = start + len(word)
            if tag == "NNP" and dry:
                if word != ("^" * len(word)):
                    annots.append((start, end))
            elif tag == "NNP":
                if word not in Scrubber.CLEANER_TAGS and ("{{%s}}" % word not in Scrubber.CLEANER_TAGS):
                    text = text[:start] + text[start:].replace(word, "{{NAME}}", 1)
        return (annots if dry else text)

    @staticmethod
    def clean_names_old(text, dry=False):
        words = Scrubber.split_re.split(text)
        tags = pos_tag([word for word in words if word])
        if dry:
            annots = []
            index_of_words_occurred = {}
            for pos, (word, tag) in enumerate(tags):
                index_of_word = words.index(word, index_of_words_occurred.get(word, 0))
                index_of_words_occurred[word] = index_of_word + 1
                empty_words_delta = len([w for w in words[:index_of_word] if w == ''])
                if tag == "NNP" and word != ("^" * len(word)):
                    start = len(" ".join(entry[0] for entry in tags[:pos])) + \
                        (0 if pos == 0 else 1) + \
                        empty_words_delta
                    end = start + len(word)
                    annots.append((start, end))
            return annots
        else:
            for word, tag in tags:
                if tag == "NNP" and word not in Scrubber.CLEANER_TAGS and ("{{%s}}" % word not in Scrubber.CLEANER_TAGS):
                    text = re.sub(r'\b%s\b' % re.escape(word), "{{NAME}}", text)
        return text

    @staticmethod
    def clean_names_regex(text, dry=False):
        if dry:
            # Using groups in names_re. To get span if individual group, use span(group_index).
            # Source: http://stackoverflow.com/a/33197759/2341189
            return [annot.span(2) for annot in Scrubber.names_re.finditer(text)]
        return Scrubber.names_re.sub(r"\1{{NAME}}", text)

    @staticmethod
    def clean_greetings(text, dry=False):
        if dry:
            return [annot.span() for annot in Scrubber.greetings_re.finditer(text)]
        return Scrubber.greetings_re.sub("{{GREETING}}", text)

    @staticmethod
    def clean_salutations(text, dry=False):
        if dry:
            return [annot.span() for annot in Scrubber.salutations_re.finditer(text)]
        return Scrubber.salutations_re.sub("{{SALUTATION}}", text)

    @staticmethod
    def clean_ips(text, dry=False):
        if dry:
            return [annot.span() for annot in Scrubber.ips_re.finditer(text)]
        return Scrubber.ips_re.sub("{{IP}}", text)

    @staticmethod
    def clean_non_english(text, dry=False):
        start = -1
        end = -1
        non_english_ranges = []
        tag_len = len("{{NON_ENGLISH}}")
        for pos, char in enumerate(text):
            if ord(char) > 128:
                if start == -1:
                    # Set both in case if there is only one special character.
                    start = pos
                    end = pos
                else:
                    end = pos
            else:
                if start != -1:
                    non_english_ranges.append((start, end))
                    start = -1
                    end = -1
        if start != -1:
            non_english_ranges.append((start, end))
        if dry:
            non_english_ranges = [(start, end + 1) for start, end in non_english_ranges]
            return non_english_ranges
        delta_len = 0
        for start, end in non_english_ranges:
            text = (text[:start - delta_len] + "{{NON_ENGLISH}}" + text[end - delta_len + 1:])
            delta_len += (end - start + 1 - tag_len)
        return text #.decode("ascii", errors="ignore")

    @staticmethod
    def clean_dates(text, dry=False):
        if dry:
            return [annot.span() for annot in Scrubber.dates_re.finditer(text)]
        return Scrubber.dates_re.sub("{{DATE}}", text)

    @staticmethod
    def clean_times(text, dry=False):
        if dry:
            return [annot.span() for annot in Scrubber.times_re.finditer(text)]
        return Scrubber.times_re.sub("{{TIME}}", text)

def main():
    if not args.inpf or not os.path.isfile(args.inpf):
        while True:
            print("Enter a line with PIIs ...")
            line = input()
            if args.dryrun:
                line, annots = Scrubber.dry_clean(line)
                print("\n%s`%s\n" % (line, annots))
            else:
                print("\n" + Scrubber.clean(line) + "\n\n")
    else:
        inp = open(args.inpf)
        out = open("custom_scrubber.csv" if not args.outf else args.outf, "w")
        for line in inp:
            #out.write("Original unscrubbed`%s\n" % (line))
            if args.dryrun:
                line, annots = Scrubber.dry_clean(line)
                out.write("Scrubbed`%s`%s\n\n" % (line, annots))
            else:
                line = Scrubber.clean(line)
                out.write("Scrubbed`%s\n\n" % line)
        inp.close()
        out.close()

if __name__ == "__main__":
    main()
