"""Merges graphs together, to stitch together graphs that were
split apart across different bro logs.

This script will create two new files for every input file, a '.changed' and a
'.unchanged' version, the former containg bro graphs that contain at least the
records from at least two graphs in the input file, and the second containg
graphs that are unchanged from the merge operation."""

import sys
import os
import brotools.reports
import brotools.records
from brotools.graphs import merge

try:
    import cPickle as pickle
except:
    import pickle

parser = brotools.reports.default_cli_parser(sys.modules[__name__].__doc__)
parser.add_argument('--time', '-t', type=float, default=10,
                    help="The number of seconds that can pass between " +
                    "requests for them to still be counted in the same graph.")
parser.add_argument('--light', '-l', action="store_true",
                    help="If this argument is passed, the input files will " +
                    "be deleted after the merge operation.")
count, ins, out, debug, args = brotools.reports.parse_default_cli_args(parser)

debug("Preparing to read {0} collections of graphs".format(count))

counts = {
    "in" : 0,
    "out" : 0
}

parsed_files = []
for path, graph, is_changed, state in merge(ins(), args.time, state=True):
    if args.light and path in parsed_files and path != parsed_files[-1]:
        try:
            os.remove(path)
        except OSError:
            pass

    counts['out'] += 1
    counts['in'] = state['count']
    if is_changed:
        with open(path + ".changed", 'a') as h:
            pickle.dump(graph, h)
    else:
        with open(path + ".unchanged", 'a') as h:
            pickle.dump(graph, h)
    if path not in parsed_files:
        parsed_files.append(parsed_files)

if args.light:
    for prev_path in parsed_files:
        try:
            os.remove(prev_path)
        except OSError:
            pass

out.write("""Changed: {}
Unchanged: {}
Merges: {}
Count: {}\n""".format(state['# changed'], state['# unchanged'], state['merges'], state['count']))
out.write("Found graphs: {0}\n".format(counts['in']))
out.write("Written graphs: {0}\n".format(counts['out']))
