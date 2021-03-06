#!/usr/bin/env python
"""Performs a merge of several gziped files of bro log data, and outputs the
count of records contained in all merged graphs.  This script exists mainly
to make sure that we're not loosing records in the merge process.

The script reads paths to gziped bro logs from stdin, with each file appearing
on its own line.
"""
import sys
import os.path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from brotools.reports import record_filter
from brotools.merge import merge, group_records
from brotools.graphs import graphs
import tempfile

files_to_merge = sys.stdin.read().strip().split()
grouped_files = group_records(files_to_merge)
temp_dir = tempfile.mkdtemp()

count = 0
for orig_files, dest_file in grouped_files:
    merge(orig_files, os.path.join(temp_dir, dest_file))
    with open(os.path.join(temp_dir, dest_file), 'r') as h:
        count += sum([len(g) for g in graphs(h, record_filter=record_filter)])
print count
