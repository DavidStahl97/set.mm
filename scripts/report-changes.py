#!/bin/python3
# Report changes to Metamath .mm file
# (C) 2019 David A. Wheeler
# This script is released as open source software under the MIT license.
# SPDX-License-Identifier: MIT

# To make this runnable, first install Python3.
# Ensure pip3 is installed by running "python3 -m ensurepip".
# Then install "ply" library: "pip3 install ply"
# We use "ply" to implement easy lexing of the data.

# To use this to generate a Gource presentation:
# scripts/report-changes.py > changes.log
# sort -n changes.log > changes-sorted.log
# gource --load-config scripts/gource.config changes-sorted.log
#
# For a video file, modify the "gource" command to add "-o gource.ppm", then:
# ffmpeg -y -r 30 -f image2pipe -vcodec ppm -i gource.ppm -pix_fmt yuv420p \
#        -threads 0 -bf 0 gource.mp4
#
# If you want music, you need to download some. Here's what I used:
# Music by audionautix.com - "Threshold" by Jason Shaw, CC-BY-3.0 Unported.
# wget https://audionautix.com/Music/Threshold.mp3
# ffmpeg -i gource.mp4 -i Threshold.mp3 -c:v copy -c:a aac \
#        -strict experimental -filter:a "volume=0.6" gource-muxed.mp4
#
#
# This was recommended but it did not work for me:
# ffmpeg -y -r 60 -f image2pipe -vcodec ppm -i gource.ppm -vcodec libx264 \
#        -preset medium -pix_fmt yuv420p -crf 1 -threads 0 -bf 0 gource.mp4

# By default, output the Gource custom log format.
# https://github.com/acaudwell/Gource/wiki/Custom-Log-Format
# timestamp|username|type ((A)dded, (M)odified, (D)eleted)|file path|color

# Be sure to "sort -n" its output.
# Also get: http://us.metamath.org/mmlogo.svg

# TODO: This doesn't handle multiple-person contributions well (and or "/")

import ply.lex as lex

import datetime
import re

OUTPUT_FORMAT = 'gource'
MMFILE = 'set.mm'

tokens = (
    'ACTION',
    'ASSERTION',
    'HEADING1',
    'HEADING2',
    'HEADING3',
    'HEADING4',
    'BORING',
)

# Define patterns. WARNING: Ply uses Python's VERBOSE mode, so bare
# spaces are *ignored* (use \s) and "#" must be matched using [#].

def t_ACTION(t):
    r'''
      \(
         (Contributed|Proof shortened|Modified|Revised)\s+
         by\s+([^()]+),\s+
         ([0-9]+-[A-Za-z]{3}-[0-9]{4,})\.?
      \)'''
    # Contributed, Name, Date
    t.value = t.lexer.lexmatch.group(2,3,4)
    return t

def t_ASSERTION(t):
    r'[^ ]+\s+\$[ap]\s\|-\s'
    t.value = t.value.split()[0] # Return just the label
    return t

def t_HEADING1(t):
    # #define HUGE_DECORATION "####"
    r'''[#][#][#][#][#][#][#][#][^\n]* \n
        [^\n]+ \n
        \s* [#][#][#][#][#][#][#][#][^\n]* \n'''
    t.value = t.value.split('\n')[1].strip()
    return t

def t_HEADING2(t):
    # #define BIG_DECORATION "#*#*"
    r'''[#][*][#][*][#][*][#][*][^\n]* \n
        [^\n]+ \n
        \s* [#][*][#][*][#][*][#][*][^\n]* \n'''
    t.value = t.value.split('\n')[1].strip()
    return t

def t_HEADING3(t):
    # #define SMALL_DECORATION "=-=-"
    r'''=-=-=-[^\n]* \n
        [^\n]+ \n
        \s* =-=-=-[^\n]* \n'''
    t.value = t.value.split('\n')[1].strip()
    return t

def t_HEADING4(t):
    # #define TINY_DECORATION "-.-."
    r'''-\.-\.[^\n]* \n
        [^\n]+ \n
        \s* -\.-\.[^\n]* \n'''
    t.value = t.value.split('\n')[1].strip()
    return t

# We ignore "boring" words (sequences of nonspaces) for speed.
# Python is slow; handling word-at-a-time means we do far less work.
# This is a short regex, and thus has a lower precedence.
t_ignore_BORING = r'[^\s]+'

# Ignored characters (whitespace)
t_ignore  = ' \t\n'

# Skip everything else
def t_error(t):
    print("Illegal character '%s'" % t.value[0])
    t.lexer.skip(1)

def section_name(heading):
    # Like join, but skip [0] and ignore None
    result = heading[1]
    for next_part in heading[2:]:
        if next_part is not None:
            result += '/'
            result += next_part
    return result

# Turn multiple whitespace into a single space.
def cleanup_whitespace(text):
    return ' '.join(text.strip().split())

MONTHS = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}

def cleanup_date(date):
    day, text_month, year = date.strip().split('-')
    month = MONTHS[text_month]
    day = int(day)
    return f"{year}-{month:02d}-{day:02d}"

POSIX_EPOCH = datetime.datetime(1970, 1, 1)

def timestamp_of(date):
    "Given date (in text), return # seconds since beginning of POSIX_EPOCH"
    year, month, day = date.split('-')
    dt = datetime.datetime(int(year), int(month), int(day))
    return int((dt - POSIX_EPOCH) / datetime.timedelta(seconds=1))

# For now, hand-jam name abbreviations

NAME_ABBREVIATIONS = {
    'AV': 'Alexander van der Vekens',
    'BJ': 'Benoit Jubin',
    'DAW': 'David A. Wheeler',
    'FL': 'Frédéric Liné',
    'Frederic Line': 'Frédéric Liné',
    'GL': 'Gérard Lang',
    'G&eacute;rard Lang': 'Gérard Lang',
    'JJ': 'Jerry James',
    'NM': 'Norman Megill',
    'SF': 'Scott Fenton',
    'SO': 'Stefan O\'Rear',
}

REMOVE_DEPENDENCY = re.compile('to remove dependency on .*')
EXTRA_BY = re.compile('(by )+')

def cleanup_name(name):
    name = cleanup_whitespace(name)
    # Remove "to remove dependency on ax-6 and ax-8"
    name = REMOVE_DEPENDENCY.sub('', name)
    # Remove extra by
    name = EXTRA_BY.sub('', name)
    if name in NAME_ABBREVIATIONS:
        name = NAME_ABBREVIATIONS[name]
    return name

# Begin

lexer = lex.lex()

# Read in data & pass to lexer
with open(MMFILE, 'r') as content_file:
    data = content_file.read()
lexer.input(data)

# We'll ignore heading[0] and count from 1.
heading = [None, None, None, None, None]

# Tokenize
for tok in lexer:
    if tok.type == 'HEADING1':
        heading[1] = tok.value
        heading[2] = heading[3] = heading[4] = None
    elif tok.type == 'HEADING2':
        heading[2] = tok.value
        heading[3] = heading[4] = None
    elif tok.type == 'HEADING3':
        heading[3] = tok.value
        heading[4] = None
    elif tok.type == 'HEADING4':
        heading[4] = tok.value
    elif tok.type == 'ACTION':
        last_action = tok.value
    elif tok.type == 'ASSERTION':
        # Generate output for this assertion.
        # print(heading[1], '|', last_action, '|', tok.value)
        contributed, who, date = last_action
        contributed = cleanup_whitespace(contributed)
        who = cleanup_name(who)
        date = cleanup_date(date)
        label = tok.value.strip()
        section = section_name(heading)
        if OUTPUT_FORMAT == 'gource':
            timestamp = timestamp_of(date)
            local_name = section + '/' + label
            if contributed == 'Contributed':
                contribution_type = 'A'
            else:
                contribution_type = 'M'
            # timestamp|username|type ((A)dded, (M)odified, (D)eleted)|
            # file path|color
            print(f'{timestamp}|{who}|{contribution_type}|{local_name}')
        else:
            print(f'{date}|{who}|{contributed}|{label}|{section}')
    else:
        print('UNKNOWN', tok)
