from scrubber import Scrubber
import argparse
import copy
import json
import re

parser = argparse.ArgumentParser(description='Script to test scrubber recall. Takes json file generated from MIST tool with manually marked PIIs as input.')
parser.add_argument("--inpf", type=str, help="Absolute file path.", required=True)
args = parser.parse_args()

total_number_of_docs = 0
docs_with_all_pii_detected = 0
docs_with_partially_detected_pii = 0
docs_with_full_missed_pii = 0


def merge_consecutive_markings(annots):
    # Merges close markings into one. Ex:
    # [[0,8], [9,14], [20,24]] will be converted to [[0,14], [20,24]]
    if not annots:
        return annots
    new_annots = [annots[0]]
    new_annots_index = 0
    for annot in annots[1:]:
        if (annot[0] - new_annots[new_annots_index][1]) <= 1:
            new_annots[new_annots_index][1] = annot[1]
        else:
            new_annots.append(annot)
            new_annots_index += 1
    return new_annots

def print_coverage(line, marked_annots, script_annots, fully_covered_annots, partially_covered_annots, fully_missed_annots):
    print line
    print "------------------------------------------"
    print "Total marked PIIs: %s %s" % (len(marked_annots), [line[start:end] for start, end in marked_annots])
    print "Total detected PIIs: %s %s" % (len(script_annots), [line[start:end] for start, end in script_annots])
    print "Fully missed PIIs count: %s %s" % (len(fully_missed_annots), [line[start:end] for start, end in fully_missed_annots])
    print "Fully detected PIIs count: %s %s" % (len(fully_covered_annots), [line[start:end] for start, end in fully_covered_annots])
    print "Partially detected PIIs count: %s %s" % (len(partially_covered_annots), [line[start:end] for start, end in partially_covered_annots])
    print "------------------------------------------"
    print "\n\n"

def check_converage(line, marked_annots, script_annots):
    marked_chars = sum(end - start for start, end in marked_annots)
    script_chars = sum(end - start for start, end in script_annots)

    global total_number_of_docs, docs_with_all_pii_detected, docs_with_partially_detected_pii, docs_with_full_missed_pii
    total_number_of_docs += 1
    if not marked_annots and not script_annots:
        docs_with_all_pii_detected += 1
        print_coverage(line, [], [], [], [], [])
        return
    elif not marked_annots and script_annots:
        docs_with_all_pii_detected += 1
        print_coverage(line, [], script_annots, [], [], [])
        return
    elif marked_annots and not script_annots:
        docs_with_full_missed_pii += 1
        print_coverage(line, marked_annots, [], [], [], marked_annots)
        return
    orig_marked_annots = copy.deepcopy(marked_annots)
    orig_script_annots = copy.deepcopy(script_annots)
    fully_covered_annots = []
    partially_covered_annots = []
    fully_missed_annots = []
    m_annot = marked_annots[0]
    s_annot = script_annots[0]
    while True:
        if m_annot and not s_annot:
            fully_missed_annots.append(marked_annots.pop(0))
            m_annot = (marked_annots[0] if marked_annots else None)
        elif (not m_annot and s_annot) or (not m_annot and not s_annot):
            break
        elif (m_annot[0] >= s_annot[0] and m_annot[1] <= s_annot[1]):
            # Fully covered case.
            # Marked: ---------  OR -----    OR     -----  OR    ----
            # Script: ---------     --------     --------     ----------
            fully_covered_annots.append(marked_annots.pop(0))
            m_annot = (marked_annots[0] if marked_annots else None)
        elif (m_annot[1] <= s_annot[0]):
            # Fully missed case.
            # Marked: -----
            # Script:       ----
            fully_missed_annots.append(marked_annots.pop(0))
            m_annot = (marked_annots[0] if marked_annots else None)
        elif (m_annot[0] >= s_annot[1]):
            # Script not yet there case.
            # Marked:       ------
            # Script: -----
            script_annots.pop(0)
            s_annot = (script_annots[0] if script_annots else None)
        elif (m_annot[0] < s_annot[0] and m_annot[1] <= s_annot[1]):
            # Partially covered case.
            # Marked: -------    OR -----------
            # Script:    -------       --------
            partially_covered_annots.append(marked_annots.pop(0))
            m_annot = (marked_annots[0] if marked_annots else None)
        elif (m_annot[0] >= s_annot[0] and m_annot[1] > s_annot[1]):
            # Partially covered case.
            # Marked:    -------  OR  -----------
            # Script: ------          ------
            partially_covered_annots.append(marked_annots.pop(0))
            script_annots.pop(0)
            m_annot = (marked_annots[0] if marked_annots else None)
            s_annot = (script_annots[0] if script_annots else None)
        elif (m_annot[0] < s_annot[0] and m_annot[1] > s_annot[1]):
            # Partially covered case.
            # Marked: ------------
            # Script:    ------
            partially_covered_annots.append(marked_annots.pop(0))
            script_annots.pop(0)
            m_annot = (marked_annots[0] if marked_annots else None)
            s_annot = (script_annots[0] if script_annots else None)
    assert not m_annot, "All annotations not considered."
    print_coverage(line, orig_marked_annots, orig_script_annots, fully_covered_annots, partially_covered_annots, fully_missed_annots)
    docs_with_all_pii_detected += (1 if len(orig_marked_annots) ==  len(fully_covered_annots) else 0)
    if fully_missed_annots:
        docs_with_full_missed_pii += 1
    elif partially_covered_annots:
        docs_with_partially_detected_pii += 1

def main():
    inp_json = open(args.inpf).read()
    inp_json = json.loads(inp_json)

    text = inp_json["signal"]
    annots = []
    for aset in inp_json["asets"]:
        if aset["type"] == "PERSON":
            annots = aset["annots"]
    annots.sort(key=lambda k: k[0])
    text = text.encode("utf-8").decode("utf-8")
    text = text.strip()
    text = text.replace("\r\n", "^^\n")

    current_annot = (annots[0] if annots else None)
    processed_length = 0
    for line in text.split('\n'):
        if not line:
            continue
        script_annots = Scrubber.dry_clean(line)[1]
        if not current_annot:
            continue
        line_len = len(line)
        line_annots = []
        while True:
            if not current_annot:
                break
            start = current_annot[0] - processed_length
            end = current_annot[1] - processed_length
            if (start <= line_len and end <= line_len):
                annots.pop(0)
                line_annots.append([start, end])
                current_annot = (annots[0] if annots else None)
            else:
                break
        processed_length += len(line)
        line_annots = merge_consecutive_markings(line_annots)
        script_annots = merge_consecutive_markings(script_annots)
        check_converage(line, line_annots, script_annots)
    print "Total number of docs: %s" % total_number_of_docs
    print "Docs with no PIIs / all PIIs detected: %s" % docs_with_all_pii_detected
    print "Docs with only partially missed PIIs: %s" % docs_with_partially_detected_pii
    print "Docs with fully missed PIIs: %s" % docs_with_full_missed_pii

if __name__ == "__main__":
    main()
