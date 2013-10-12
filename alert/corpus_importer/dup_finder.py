from collections import OrderedDict
from lxml import html
import os
from lxml.html import tostring

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import sys
execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)

from django import db
from django.conf import settings
from alert.search.models import Document
from alert.lib import sunburnt
from alert.lib.encode_decode import num_to_ascii
from cleaning_scripts.lib.string_diff import find_confidences, gen_diff_ratio
import datetime
from datetime import date
import re

DEBUG = True

def build_date_range(date_filed, range=5):
    """Build a date range to be handed off to a solr query

    """
    after = date_filed - datetime.timedelta(days=5)
    before = date_filed + datetime.timedelta(days=6)
    date_range = '[%sZ TO %sZ]' % (after.isoformat(),
                                   before.isoformat())
    return date_range


def load_stopwords():
    """Loads Sphinx's stopwords file.

    Pulls in the top 5000 words as generated by Sphinx, and returns them as
    an array.
    """
    stopwords = []
    with open('%s/alert/corpus_importer/word_freq.5000.txt' % INSTALL_ROOT, 'r') as stopwords_file:
        for word in stopwords_file:
            stopwords.append(word.strip().decode('utf-8'))
    return stopwords
stopwords = load_stopwords()  # Module-level.


def get_good_words(word_list, stop_words_size=500):
    """Cleans out stop words, abbreviations, etc. from a list of words"""
    good_words = []
    for word in word_list:
        # Clean things up
        word = re.sub(r"'s", '', word)
        word = word.strip('*,();"')

        # Boolean conditions
        stop = word in stopwords[:stop_words_size]
        bad_stuff = re.search('[0-9./()!:&\']', word)
        too_short = True if len(word) <= 1 else False
        if any([stop, bad_stuff, too_short]):
            continue
        else:
            good_words.append(word)
    # Eliminate dups, but keep order.
    return list(OrderedDict.fromkeys(good_words))


def make_solr_query(content, caseName, court, date_filed, num_q_words=0, encoding='utf-8', DEBUG=False):
    """Grab words from the content and returns them to the caller.

    This function attempts to choose words from the content that would return
    the fewest cases if queried. Words are selected from the case name and the
    content.
    """
    main_params = {'fq': ['court_exact:%s' % court,
                          'dateFiled:%s' % build_date_range(date_filed)],
                   'rows': 100,
                   'q': ''}

    # 1. Create the case name query.
    case_name_q_words = []
    case_name_words = caseName.lower().split()
    if ' v. ' in caseName.lower():
        v_index = case_name_words.index('v.')
        # The first word of the defendant and the last word in the plaintiff that's
        # not a bad word.
        plaintiff_a = get_good_words(case_name_words[:v_index])
        defendant_a = get_good_words(case_name_words[v_index + 1:])
        if plaintiff_a:
            case_name_q_words.append(plaintiff_a[-1])
        if defendant_a:
            case_name_q_words.append(defendant_a[0])
    elif 'in re ' in caseName.lower() or 'matter of ' in caseName.lower():
        try:
            subject = re.search('(?:(?:in Re)|(?:matter of)) (.*)', caseName, re.I).group(1)
        except TypeError:
            subject = ''
        if subject:
            case_name_q_words.append(subject.split()[0])
    if case_name_q_words:
        main_params['q'] = 'caseName:(%s) ' % ' '.join(case_name_q_words)

    # 2. Add num_q_words to the query.
    i = 1
    query_words = []
    good_words = get_good_words(content.split(), stop_words_size=2500)  # Low tolerance for stopwords
    while i <= num_q_words and i < len(good_words):
        new_word = good_words[i].decode(encoding).encode('utf-8').lower()
        if new_word in case_name_q_words:
            i += 1
            continue
        else:
            query_words.append(new_word)
            i += 1
    if query_words:
        main_params['q'] += ' '.join(query_words)

    if DEBUG:
        print "    - main_params are: %s" % main_params

    return main_params


def get_dup_stats(doc):
    """The heart of the duplicate algorithm. Returns stats about the case as
    compared to other cases already in the system. Other methods can call this
    one, and can make decisions based on the stats generated here.

    If no likely duplicates are encountered, stats are returned as zeroes.

    Process:
        1. Refine the possible result set down to just a few candidates.
        2. Determine their likelihood of being duplicates according to a
           number of measures:
            - Similarity of case name
            - Similarity of docket number
            - Comparison of content length
    """
    stats = []
    DEBUG = True

    ######################################
    # 1: Refine by date, court and words #
    ######################################
    num_q_words = 5

    # Add one word to the query until either you run out of words or you get less than 5 results.
    result_count = 6
    word_count = len(doc.body_text.split())
    while result_count > 5 and num_q_words <= word_count:
        main_params = make_solr_query(
            doc.body_text,
            doc.citation.case_name,
            doc.court_id,
            doc.date_filed,
            num_q_words,
            encoding='cp1252',
            DEBUG=DEBUG,
        )
        conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
        candidates = conn.raw_query(**main_params).execute()
        result_count = len(candidates)
        if main_params['q'].startswith('caseName'):
            # We've exhausted the possibilities for this case. Need to move on
            # regardless of count.
            break
        else:
            num_q_words += 1

    stats.append(result_count)
    if result_count == 0:
        return stats, candidates

    #########################################
    # 2: Attempt filtering by docket number #
    #########################################
    # Two-step process. First we see if we have any exact hits.
    # Second, if there were exact hits, we forward those onwards. If not, we
    # forward everything.
    remaining_candidates = []
    if doc.citation.docket_number:
        new_docket_number = re.sub("(\D|0)", "", doc.citation.docket_number)
        for candidate in candidates:
            if candidate.get('docketNumber'):
                # Get rid of anything in the docket numbers that's not a digit
                result_docket_number = re.sub("(\D|0)", "", candidate['docketNumber'])
                # Get rid of zeroes too.
                if new_docket_number == result_docket_number:
                    remaining_candidates.append(candidate)

    if len(remaining_candidates) > 0:
        # We had one or more exact hits! Use those.
        candidates = remaining_candidates
    else:
        # We just let candidates from step one get passed through by doing nothing.
        pass
    stats.append(len(candidates))

    ##############################
    # 3: Find the best case name #
    ##############################
    confidences = find_confidences(candidates, doc.citation.case_name)
    stats.append(confidences)

    ###########################
    # 4: Check content length #
    ###########################
    percent_diffs, gestalt_diffs = [], []
    new_stripped_content = re.sub('\W', '', doc.body_text).lower()
    for candidate in candidates:
        candidate_stripped_content = re.sub('\W', '', candidate['text']).lower()

        # Calculate the difference in text length and their gestalt difference
        length_diff = abs(len(candidate_stripped_content) - len(new_stripped_content))
        percent_diff = float(length_diff) / len(new_stripped_content)
        percent_diffs.append(percent_diff)
        gestalt_diffs.append(gen_diff_ratio(candidate_stripped_content, new_stripped_content))

    stats.append(percent_diffs)
    stats.append(gestalt_diffs)

    return stats, candidates


def write_dups(source, dups, DEBUG=False):
    """Writes duplicates to a file so they are logged.

    This function receives a queryset and then writes out the values to a log.
    """
    log = open('dup_log.txt', 'a')
    if dups[0] is not None:
        log.write(str(source.pk))
        print "  Logging match: " + str(source.pk),
        for dup in dups:
            # write out each doc
            log.write('|' + str(dup.pk) + " - " + num_to_ascii(dup.pk))
            if DEBUG:
                print '|' + str(dup.pk) + ' - ' + num_to_ascii(dup.pk),
    else:
        log.write("  No dups found for %s" % source.pk)
        if DEBUG:
            print "  No dups found for %s" % source.pk
    print ''
    log.write('\n')
    log.close()


def import_and_report_records():
    """Traverses the first 500 records and find their dups.

    This script is used to find dups within the database by comparing it to
    the Sphinx index. This simulates the duplicate detection we will need to
    do when importing from other sources, and allows us to test it.
    """

    docs = Document.objects.filter(court='ca1')[:5000]
    #docs = Document.objects.filter(pk = 985184)

    # do this 1000 times
    for doc in docs:
        court = doc.court_id
        date = doc.date_filed
        casename = doc.citation.caseNameFull
        docket_number = doc.citation.docket_number
        content = doc.plain_text
        id = num_to_ascii(doc.pk)
        if content == "":
            # HTML content!
            content = doc.html
            br = re.compile(r'<br/?>')
            content = br.sub(' ', content)
            p = re.compile(r'<.*?>')
            content = p.sub('', content)

        dups = check_dup(court, date, casename, content, docket_number, id, True)

        if len(dups) > 0:
            # duplicate(s) were found, write them out to a log
            write_dups(doc, dups, True)

        if DEBUG:
            print ''
        # Clear query cache, as it presents a memory leak when in dev mode
        db.reset_queries()

    return


def main():
    print import_and_report_records()
    print "Completed 500 records successfully. Exiting."
    exit(0)


if __name__ == '__main__':
    main()

