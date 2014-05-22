"""Classes and iterators useful for processing collections of bro data"""

def _strip_protocol(url):
    if url[0:7] == "http://":
        url = url[7:]
    elif url[0:8] == "https://":
        url = url[8:]
    return url


def bro_chains(handle, time=.5, record_filter=None):
    """A generator function that yields completed BroRecordChain objects.

    Args:
        handle -- a file handle like object to read lines of bro data off of.

    Keyword Args:
        record_filter -- an optional function that, if provided, should take two
                         arguments of bro records, and should provide True if
                         they should be included in the same chain or not.  Note
                         that this is in addition to the filtering / matching
                         already performed by the BroRecordChain.add_record
                         function
        time          -- the maximum amount of time that can elapse between two
                         records and still have them be considered in the same
                         chain

    Return:
        An iterator returns BroRecordChain objects
    """
    chains = []
    latest_record_time = 0
    for r in bro_records(handle):

        short_content_type = r.content_type[:9]
        if short_content_type not in ('text/plai', 'text/html') or r.status_code == "301":
            continue

        # A growing timestamp of the most recent record found yet.  Since
        # records are required to be ordered (handled elsewhere), we know
        # that the current record being examined will always be the most recent
        # one / latest one
        latest_record_time = r.ts

        # Since we don't allow a step greater than the passed time parameter
        # between any two records in a chain, we know we're done considering
        # any chains who have their most recent record being more than `time`
        # ago
        early_record_cutoff = latest_record_time - time

        # First see if there are any chains that this record can be attached
        # to in the current collection
        altered_chain = None
        first_good_chain_index = None
        index = 0
        for c in chains:
            if not altered_chain and c.add_record(r, record_filter):
                altered_chain = c

            # In order to avoid having to double walk the set of chains,
            # we check here to find the first chain in the set that happened
            # recently enough to not need to evicted
            if first_good_chain_index is None and c.tail().ts > early_record_cutoff:
                first_good_chain_index = index

            if altered_chain and first_good_chain_index is not None:
                break

            index += 1

        # If we couldn't attach the current record to an existing chain,
        # create a new chain with this record as the root
        if altered_chain is None:
            chains.append(BroRecordChain(r))
            first_good_chain_index = len(chains) - 1
        # Otherwise, move the updated chain to the end of the chain list,
        # so that the last updated record is always the first in the
        # list of chains
        else:
            chains.remove(altered_chain)
            chains.append(altered_chain)

        # Now, return any completed chains that have been found, which
        # just means any chains that have their last element more than
        # the given cut off time ago.
        if first_good_chain_index is None:
            for completed_c in chains:
                yield c
            chains = []
        else:
            for completed_c in chains[:first_good_chain_index]:
                yield completed_c
            chains = chains[first_good_chain_index:]

    # Once we've finished processing all bro records in the set,
    # there will likely still be some chains that haven't been completed.
    # Return them all here
    for remaining_chain in chains:
        yield remaining_chain


def bro_records(handle):
    """A generator function for iterating over a a collection of bro records.
    The iterator returns BroRecord objects (named tuples) for each record
    in the given file

    Args:
        handle -- a file handle like object to read lines of bro data off of.

    Return:
        An iterator returning BroRecord objects
    """
    seperator = None
    for raw_row in handle:
        row = raw_row[:-1] # Strip off line end
        if not seperator and row[0:10] == "#separator":
            seperator = row[11:].decode('unicode_escape')
        elif row[0] != "#":
            try:
                r = BroRecord(row, seperator)
            except Exception, e:
                print "Bad line entry"
                print "File: {0}".format(handle.name)
                print "Values: {0}".format(row.split(seperator))
                raise e
            yield r


class BroRecord(object):

    def __init__(self, line, seperator="\t"):
        values = [a if a != "-" else "" for a in line.split(seperator)]
        self.ts = float(values[0])
        self.id_orig_h = values[1]
        self.id_resp_h = values[2]
        self.method = values[3]
        self.host = values[4]
        self.uri = values[5]
        self.referrer = _strip_protocol(values[6])
        self.user_agent = values[7]
        self.status_code = values[8]
        self.content_type = values[9]
        self.location = values[10]
        try:
            self.cookies = values[11]
        except IndexError:
            self.cookies = None
        self.line = line

    def __str__(self):
        return self.line

    def url(self):
        return u"{host}{uri}".format(host=self.host, uri=self.uri)

class BroRecordChain(object):
    """Keeps track of a chain of BroRecord items, based on ip, referrer and
    timestamp"""

    def __init__(self, record):
        self.ip = record.id_orig_h
        self.tail_url = record.host + record.uri
        self.records = [record]

    def __str__(self):
        output = "ip: {0}\n".format(self.ip)
        count = 0
        for r in self.records:
            output += ("    " * count) + (" -> " if count else "") + r.host + r.uri + " ({0})\n".format(r.ts)
            count += 1
        return output

    def __iter__(self):
        return iter(self.records)

    def domains(self):
        """Returns a list of the distinct domains represented in the current
        redirection chain.  Each domain will only appear in the list once,
        in the order they appeared in the redirection chain (earliest to
        latest).

        Return:
            A list of zero or more unique domains in the redirection chain
        """
        hosts = []
        for r in self:
            if r.host not in hosts:
                hosts.append(r.host)
        return hosts

    def head(self):
        return self.records[0]

    def tail(self):
        return self.records[-1]

    def len(self):
        return len(self.records)

    def add_record(self, record, record_filter=None, ignore_self_refs=True):
        """Attempts to add a given BroRecord to the current referrer chain.
        This method checks to see if it makes sense to add the given record
        to the referrer chain (by checking the ip of the requester, whether
        the referrer of the given record matches the domain + path of the
        last record in this chain, and if the record comes after the
        last the record in the chain)

        Args:
            record -- a BroRecord element to try and add to a referrer chain

        Keyword Args:
            record_filter    -- an optional function that, if provided, should take
                                two arguments of bro records, and should provide
                                True if the record should be included
            ignore_self_refs -- sometimes pages will record references to
                                themselves (to do things like setting a cookie
                                serverside).  Setting this flag to True will
                                not include these self references.

        Return:
            True if the given record was added to the chain, otherwise False
        """
        if record.id_orig_h != self.ip:
            return False

        tail_record = self.tail()

        if record.ts < tail_record.ts:
            return False

        referrer_url = _strip_protocol(record.referrer)
        if ignore_self_refs and self.tail_url == record.host + record.uri:
            return False

        if self.tail_url != referrer_url:
            return False

        if record_filter and not record_filter(tail_record, record):
            return False

        self.tail_url = record.host + record.uri
        self.records.append(record)
        return True


class BroRecordWindow(object):
    """Keep track of a sliding window of BroRecord objects, and don't keep more
    than a given amount (defined by a time range) in memory at a time"""

    def __init__(self, time=.5):
        # A collection of BroRecords that all occurred less than the given
        # amount of time before the most recent one (in order oldest to newest)
        self._collection = []

        # Window size of bro records to keep in memory
        self._time = time

    def size(self):
        return len(self._collection)

    def prune(self):
        """Remove all BroRecords that occured more than self.time before the
        most recent BroRecord in the collection.

        Return:
            An int count of the number of objects removed from the collection
        """

        # Simple case that if we have no stored BroRecords, there can't be
        # any to remove
        if len(self._collection) == 0:
            return 0

        removed_count = 0
        most_recent_time = self._collection[-1].ts
        window_low_bound = self._time

        while len(self._collection) > 1 and self._collection[0].ts + window_low_bound < most_recent_time:
            self._collection = self._collection[1:]
            removed_count += 1

        return removed_count

    def append(self, record):
        """Adds a BroRecord to the current collection of bro records, and then
        cleans to watched collection to remove old records (records before the)
        the sliding time window.

        Args:
            record -- A BroRecord, created by the bro_records function

        Return:
            The number of records that were removed from the window during garbage collection.
        """
        self._collection.append(record)

        # Most of the time the given record will be later than the last
        # record added (since we keep the collection sorted).  In this common
        # case, just add the new record to the end of the collection.
        # Otherwise, add the record and sort the whole thing
        self._collection.append(record)
        if record.ts > self._collection[-2].ts:
            self._collection.sort(key=lambda x: x.ts)

        return self.prune()
