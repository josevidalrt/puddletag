# -*- coding: utf-8 -*-
import pdb, string
from collections import defaultdict
from copy import deepcopy

from puddlestuff.constants import VARIOUS
from puddlestuff.findfunc import filenametotag
from puddlestuff.functions import replace_regex
from puddlestuff.puddleobjects import natcasecmp, ratio
from puddlestuff.tagsources import RetrievalError
from puddlestuff.translations import translate
from puddlestuff.util import sorted_split_by_field, split_by_field, to_string
from puddlestuff.webdb import strip as strip_fields

def set_status(v):
    print v

NO_MATCH_OPTIONS = [
    translate('Masstagging', 'Continue'),
    translate('Masstagging', 'Stop')]

SINGLE_MATCH_OPTIONS = [
    translate('Masstagging', 'Combine and continue'),
    translate('Masstagging', 'Replace and continue'),
    translate('Masstagging', 'Combine and stop'),
    translate('Masstagging', 'Replace and stop')]

AMBIGIOUS_MATCH_OPTIONS = [
    translate('Masstagging', 'Use best match'),
    translate('Masstagging', 'Do nothing and continue')]

COMBINE_CONTINUE = 0
REPLACE_CONTINUE = 1
COMBINE_STOP = 2
REPLACE_STOP = 3

CONTINUE = 0
STOP = 1

USE_BEST = 0
DO_NOTHING = 1
RETRY = 2

ALBUM_BOUND = 'album'
TRACK_BOUND = 'track'
PATTERN = 'pattern'
SOURCE_CONFIGS = 'source_configs'
FIELDS = 'fields'
JFDI = 'jfdi'
NAME = 'name'
DESC = 'description'
EXISTING_ONLY = 'field_exists'

DEFAULT_PATTERN = u'%artist% - %album%/%track% - %title%'
DEFAULT_NAME = translate('Masstagging', 'Default Profile')


POLLING = translate("MassTagging", '<b>Polling: %s</b>')
MATCH_ARTIST_ALBUM = translate("MassTagging",
    'Retrieving matching album. <b>%1 - %2</b>')
MATCH_ARTIST = translate("MassTagging",
    'Retrieving matching album. Artist=<b>%1</b>')
MATCH_ALBUM = translate("MassTagging",
    'Retrieving matching album. Album=<b>%1</b>')
MATCH_NO_INFO = translate("MassTagging", 'Retrieving matching album.')

SEARCHING_ARTIST_ALBUM = translate("MassTagging",
    ':insertStarting search for: <br />artist=<b>%1</b> '
    '<br />album=<b>%2</b><br />')
SEARCHING_ARTIST = translate("MassTagging",
    ':insertStarting search for: <br />artist=<b>%1</b>'
    '<br />album=No album name found.')
SEARCHING_ALBUM = translate("MassTagging",
    ':insertStarting search for: <br />album=<b>%1</b>'
    '<br />artist=No artist found.')
SEARCHING_NO_INFO = translate("MassTagging",
    ':insertNo artist or album info found in files. Starting search.')

RESULTS_FOUND = translate("MassTagging", '<b>%d</b> results found.')
NO_RESULTS_FOUND = translate("MassTagging", '<b>No results were found.</b>')
ONE_RESULT_FOUND = translate("MassTagging", '<b>One</b> result found.')

MATCHING_ALBUMS_FOUND = translate("MassTagging",
    '<b>%d</b> possibly matching albums found.')
ONE_MATCHING_ALBUM_FOUND = translate("MassTagging",
    '<b>One</b> possibly matching album found.')
NO_MATCHES = translate("MassTagging",
    'No matches found for tag source <b>%s</b>')

RETRIEVING_NEXT = translate("MassTagging",
    'Previously retrieved result does not match. '
    'Retrieving next matching album.')

RECHECKING = translate("MassTagging",
    '<br />Rechecking with results from <b>%s</b>.<br />')

VALID_FOUND = translate("MassTagging",
    'Valid matches were found for the album.')

NO_VALID_FOUND = translate("MassTagging",
    '<b> No valid matches were found for the album.</b>')

class MassTagFlag(object):
    def __init__(self):
        self.stop = False
        object.__init__(self)

def apply_regexps(audio, regexps):
    audio = deepcopy(audio)
    for field, (regexp, output) in regexps.iteritems():
        if field not in audio:
            continue
        text = to_string(audio[field])
        try:
            val = replace_regex(text, regexp, output)
            if val:
                audio[field] = val
        except puddlestuff.findfunc.FuncError:
            continue
    return audio

def brute_force_results(audios, retrieved):
    matched = {}

    audios = sorted(audios, natcasecmp,
        lambda f: to_string(f.get('track', f['__filename'])))

    retrieved = sorted(retrieved, natcasecmp,
        lambda t: to_string(t.get('track', t.get('title' , u''))))

    for audio, result in zip(audios, retrieved):
        matched[audio] = result

    return matched

def check_result(result, audios):
    track_nums = filter(None,
        [to_string(audio.get('track', None)) for audio in audios])

    if track_nums:
        max_num = 0
        for num in track_nums:
            try: num = int(num)
            except (TypeError, ValueError): continue
            max_num = num if num > max_num else max_num
        if max_num != 0 and max_num == len(result.tracks):
            return True

    if result.tracks is None:
        return True

    if len(audios) == len(result.tracks):
        return True
    return False

def combine_tracks(track1, track2):
    ret = defaultdict(lambda: [])
    
    for key, value in track2.items() + track1.items():
        if isinstance(value, basestring):
            if value not in ret[key]:
                ret[key].append(value)
        else:
            for v in value:
                if v not in ret[key]:
                    ret[key].append(v)
    return ret

def fields_from_text(text):
    if not text:
        return []
    return filter(None, map(string.strip, text.split(u',')))

def dict_difference(dict1, dict2):
    """Returns a dictonary containing key/value pairs from dict2 where key
    isn't in dict1."""
    temp = {}
    for field in dict2:
        if field not in dict1:
            temp[field] = dict2[field]
    return temp

def find_best(matches, files, minimum=0.7):
    group = split_by_field(files, 'album', 'artist')
    album = group.keys()[0]
    artists = group[album].keys()
    if len(artists) == 1:
        artist = artists[0]
    else:
        artist = VARIOUS

    d = {'artist': artist, 'album': album}
    scores = {}

    for match in matches:
        if hasattr(match, 'info'):
            info = match.info
        else:
            info = match[0]

        totals = [ratio(d[key].lower(), to_string(info[key]).lower())
            for key in d if key in info]

        if len(totals) == len(d):
            scores[min(totals)] = match

        if match.tracks and min(totals) < minimum:
            if len(match.tracks) == len(files):
                scores[minimum + 0.01] = match

    if scores:
        return [scores[score] for score in
            sorted(scores, reverse=True) if score >= minimum]
    else:
        return []

def get_artist_album(files):
    tags = split_by_field(files, 'album', 'artist')
    album = tags.keys()[0]
    artists = tags[album]
    if len(artists) > 1:
        return VARIOUS, album
    else:
        return list(artists)[0], album

def get_match_str(info):
    artist = album = None
    if info.get('artist'):
        artist = to_string(info['artist'])

    if info.get('album'):
        album = to_string(info['album'])

    if artist and album:
        return MATCH_ARTIST_ALBUM.arg(artist).arg(album)
    elif artist:
        return MATCH_ARTIST.arg(artist)
    elif album:
        return MATCH_ALBUM.arg(album)
    else:
        return MATCH_NO_INFO

get_lower = lambda f, key, default=u'': to_string(f.get(key,default)).lower()

def ratio_compare(d1, d2, key):
    return ratio(get_lower(d1, key, u'a'), get_lower(d2, key, u'b'))

def match_files(files, tracks, minimum=0.7, keys=None, jfdi=False, existing=False):
    if not keys:
        keys = ['artist', 'title']
    ret = {}
    assigned = []
    for f in files:
        scores = {}
        for track in tracks:
            if track not in assigned:
                totals = [ratio_compare(f, track, key) for key in keys]
                score = min(totals)
                if score not in scores:
                    scores[score] = track
        if scores:
            max_ratio = max(scores)
            if max_ratio > minimum and f.cls not in ret:
                ret[f.cls] = scores[max_ratio]
                assigned.append(scores[max_ratio])

    if jfdi:
        unmatched_tracks = [t for t in tracks if t not in assigned]
        unmatched_files = [f.cls for f in files if f.cls not in ret]
        ret.update(brute_force_results(unmatched_files, unmatched_tracks))

    if existing:
        ret = dict((f, dict_difference(f, r)) for f, r in ret.iteritems())

    return ret

def merge_track(audio, info):
    track = {}

    for key in info.keys():
        if not key.startswith('#'):
            if isinstance(info[key], basestring):
                track[key] = info[key]
            else:
                track[key] = info[key][::]

    for key in audio.keys():
        if not key.startswith('#'):
            if isinstance(audio[key], basestring):
                track[key] = audio[key]
            else:
                track[key] = audio[key][::]
    return track

def merge_tsp_tracks(profiles, files=None):
    ret = []
    to_repl = []
    for tsp in profiles:
        if not tsp.matched:
            continue

        if tsp.result.tracks is None and files is not None:
            info = strip_fields(tsp.result.info, tsp.fields)
            tags = [deepcopy(info) for z in files]
        else:
            tags = [strip_fields(t, tsp.fields) for t in tsp.result.merged]

        if len(tags) > len(ret):
            ret.extend(tags[len(ret):])
        if tsp.replace_fields:
            to_repl.append([tags, tsp.replace_fields])
        for i, t in enumerate(tags):
            ret[i] = combine_tracks(ret[i], t)

    for tracks, fields in to_repl:
        for repl, track in zip(tracks, ret):
            track.update(strip_fields(repl, fields))

    return ret

def masstag(mtp, files=None, flag=None, mtp_error_func=None,
    tsp_error_func=None):

    not_found = []
    found = []

    if files is None:
        files = mtp.files

    if flag is None:
        flag = MassTagFlag()
    elif flag.stop:
        return []

    assert files

    artist, album = get_artist_album(files)

    if artist and album:
        set_status(SEARCHING_ARTIST_ALBUM.arg(artist).arg(album))
    elif artist:
        set_status(SEARCHING_ARTIST.arg(artist))
    elif album:
        set_status(SEARCHING_ALBUM.arg(album))
    else:
        set_status(SEARCHING_NO_INFO)

    for matches, results, tsp in mtp.search(files, errors=mtp_error_func):
        if flag.stop:
            break
        if len(results) > 1:
            set_status(RESULTS_FOUND % len(results))
        elif not results:
            set_status(NO_RESULTS_FOUND)
        else:
            set_status(ONE_RESULT_FOUND)

        if not matches:
            not_found.append(tsp)
            continue
        
        if len(matches) > 1:
            set_status(MATCHING_ALBUMS_FOUND % len(matches))
        else:
            set_status(ONE_MATCHING_ALBUM_FOUND)

        set_status(get_match_str(matches[0].info))
        result = tsp.retrieve(matches[0], errors=tsp_error_func)
        i = 0

        while not check_result(result, files):
            i += 1
            if i < len(matches):
                set_status(RETRIEVING_NEXT)
                result = tsp.retrieve(matches[i], errors=tsp_error_func)
            else:
                result = None
                break
        if result is None:
            set_status(NO_MATCHES % tsp.tag_source.name)
            not_found.append(tsp)
        else:
            found.append(tsp)

    ret = []

    if not_found and found:
        set_status(RECHECKING % found[0].tag_source.name)
        audios_copy = []
        for t, m in zip(map(deepcopy, files), found[0].result.merged):
            audios_copy.append(combine_tracks(t,m))

        new_mtp = MassTagProfile(translate("MassTagging", 'Rechecking'),
            files=audios_copy, profiles=not_found,
            album_bound=mtp.album_bound, track_bound=mtp.track_bound,
            regexps=mtp.regexps)

        ret = masstag(new_mtp, audios_copy, flag,
            mtp_error_func, tsp_error_func)

    if found:
        if not ret:
            set_status(VALID_FOUND)
        return [tsp.result for tsp in found] + ret
    else:
        set_status(NO_VALID_FOUND)
        return []

def split_files(audios, pattern):

    def copy_audio(f):
        tags = filenametotag(f['__path'], pattern, True)
        audio_copy = deepcopy(f)
        audio_copy.update(dict_difference(audio_copy, tags))
        audio_copy.cls = f
        return audio_copy

    tag_groups = []

    for dirpath, files in sorted_split_by_field(audios, '__dirpath'):
        album_groups = sorted_split_by_field(files, 'album')
        for album, album_files in album_groups:
            tag_groups.append(map(copy_audio, album_files))

    return tag_groups

class MassTagProfile(object):
    def __init__(self, name=DEFAULT_NAME, desc=u'', fields=None, files=None,
        file_pattern=DEFAULT_PATTERN, profiles=None, album_bound=0.50,
        track_bound=0.80, jfdi=True, leave_existing=False, regexps=''):

        object.__init__(self)

        self.album_bound = album_bound
        self.desc = desc
        self.fields = [u'artist', u'title'] if fields is None else fields
        self.file_pattern = file_pattern
        self.files = [] if files is None else files
        self.jfdi = jfdi
        self.leave_existing = leave_existing
        self.name = name
        self.profiles = profiles if profiles is not None else []
        self.regexps = regexps
        self.track_bound = track_bound

    def clear(self):
        for profile in self.profiles:
            profile.clear_results()

    def search(self, files=None, profiles=None, regexps=None, errors=None):
        files = self.files if files is None else files
        profiles = self.profiles if profiles is None else profiles
        regexps = self.regexps if regexps is None else regexps

        assert files
        assert profiles

        if regexps:
            files = map(lambda f: apply_regexps(f, regexps), files)

        for profile in profiles:
            profile.clear_results()
            set_status(POLLING % profile.tag_source.name)
            try:
                results = profile.search(files)
            except RetrievalError, e:
                if errors is None:
                    raise e
                if errors(e, profile):
                    raise e
                yield [], [], profile
                continue
                
            profile.find_matches(self.album_bound, files, results)
            yield profile.matched, profile.results, profile

class Result(object):
    def __init__(self, info=None, tracks=None, tag_source=None):
        object.__init__(self)

        self.__info = {}
        self.__tracks = []
        self.merged = []
        self.tag_source = tag_source

        self.tracks = tracks if tracks is not None else []
        self.info = {} if info is None else info

    def _get_info(self):
        return self.__info

    def _set_info(self, value):
        self.__info = value

        if self.__tracks:
            self.merged = map(lambda a: merge_track(a, value), self.__tracks)
        else:
            self.merged = []

    info = property(_get_info, _set_info)

    def _get_tracks(self):
        return self.__tracks

    def _set_tracks(self, value):
        self.__tracks = value
        self._set_info(self.__info)

    tracks = property(_get_tracks, _set_tracks)

    def retrieve(self, errors=None):
        if self.tag_source:
            try:
                self.info, self.tracks = self.tag_source.retrieve(self.info)
            except RetrievalError, e:
                if errors is None:
                    raise
                if errors(e):
                    raise e
                else:
                    return {}, []
            return self.info, self.tracks
        return {}, []
            

class TagSourceProfile(object):
    def __init__(self, files=None, tag_source=None, fields=None,
            if_no_result=CONTINUE, replace_fields=None):

        object.__init__(self)

        self.if_no_result = if_no_result
        self.fields = [] if fields is None else fields
        self.files = [] if files is None else files
        self.group_by = tag_source.group_by if tag_source else None
        self.matched = []
        self.replace_fields = [] if replace_fields is None else replace_fields
        self.result = None
        self.results = []
        self.tag_source = tag_source

    def clear_results(self):
        self.result = None
        self.results = []
        self.matched = []

    def find_matches(self, album_bound, files=None, results=None):
        files = self.files if files is None else files
        results = self.results if results is None else results

        assert files
        assert results

        self.matched = find_best(results, files, album_bound)
        return self.matched

    def retrieve(self, result, errors=None):
        info = result.info if hasattr(result, 'info') else result
        try:
            self.result = Result(*self.tag_source.retrieve(info))
        except RetrievalError, e:
            if errors is None:
                raise
            if errors(e, self):
                raise e
            else:
                self.result = Result({},[])
                
        self.result.tag_source = self.tag_source
        return self.result

    def search(self, files=None, tag_source=None):
        tag_source = self.tag_source if tag_source is None else tag_source
        files = self.files if files is None else files

        assert hasattr(tag_source, 'search')
        assert files

        files = split_by_field(files, *tag_source.group_by)
        search_value = files.keys()[0]
        self.results = map(lambda x: Result(*x),
            tag_source.search(search_value, files[search_value]))
        return self.results

if __name__ == '__main__':
    import puddlestuff.puddletag
    puddlestuff.puddletag.load_plugins()
    from puddlestuff.tagsources import tagsources
    sources = dict((t.name, t) for t in tagsources)
    source = sources['Local TSource Plugin']()
    source.applyPrefs([u'/mnt/multimedia/testlib'])
    print source._dirs
    
    
    