#!/usr/bin/env python
# encoding: utf-8

# The MIT License (MIT)

# Copyright (c) 2016-2017 CNRS

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# AUTHORS
# Hervé BREDIN - http://herve.niderb.fr

import yaml
import os.path
import warnings
import itertools
from glob import glob
from pyannote.core import Segment, Timeline


class PyannoteDatabaseException(Exception):
    pass


class FileFinder(object):
    """Database file finder

    Parameters
    ----------
    config_yml : str, optional
        Path to database configuration file in YAML format.
        See "Configuration file" sections for examples.
        Defaults to '~/.pyannote/db.yml'.

    Configuration file
    ------------------
    Here are a few examples of what is expected in the configuration file.

    # all files are in the same directory
    /path/to/files/{uri}.wav

    # support for {database} placeholder
    /path/to/{database}/files/{uri}.wav

    # support for multiple databases
    database1: /path/to/files/{uri}.wav
    database2: /path/to/other/files/{uri}.wav

    # files are spread over multiple directory
    database3:
      - /path/to/files/1/{uri}.wav
      - /path/to/files/2/{uri}.wav

    # supports * globbing
    database4: /path/to/files/*/{uri}.wav

    See also
    --------
    glob
    """

    def __init__(self, config_yml=None):
        super(FileFinder, self).__init__()

        if config_yml is None:
            config_yml = '~/.pyannote/db.yml'
        config_yml = os.path.expanduser(config_yml)

        with open(config_yml, 'r') as fp:
            self.config = yaml.load(fp)

    def _find(self, config, uri=None, database=None, **kwargs):

        found = []

        # list of path templates
        if isinstance(config, list):

            for path_template in config:
                path = path_template.format(uri=uri, database=database,
                                            **kwargs)
                found_ = glob(path)
                found.extend(found_)

        # database-indexed dictionary
        elif isinstance(config, dict):

            # if database identifier is not provided
            # or does not exist in configuration file
            # look into all databases...
            if database is None or database not in config:
                databases = list(config)
            # if database identifier is provided AND exists
            # only look into this very database
            else:
                databases = [database]

            # iteratively look into selected databases
            for database in databases:
                found_ = self._find(config[database], uri=uri,
                                    database=database, **kwargs)
                found.extend(found_)

        else:
            path_template = config
            path = path_template.format(uri=uri, database=database, **kwargs)
            found_ = glob(path)
            found.extend(found_)

        return found

    def __call__(self, current_file):
        """Find file

        Parameters
        ----------
        current_file : pyannote.database dict
            Dictionary as generated by pyannote.database plugins.

        Returns
        -------
        path : str (or list of str)
            File path or list of paths (if current_file['uri'] is a list).

        """

        # in case 'uri' contains a list of uris,
        # look for each file separately
        if isinstance(current_file.get('uri', None), list):

            uris = current_file['uri']

            # repeat 'database' if needed
            database = current_file['database']
            if isinstance(database, list):
                databases = database
            else:
                databases = itertools.repeat(database)

            # repeat 'channel' if needed
            channel = current_file.get('channel', None)
            if isinstance(channel, list):
                channels = channel
            else:
                channels = itertools.repeat(channel)

            found = []
            i = dict(current_file)

            # look for each file separately
            for uri, database, channel in zip(uris, databases, channels):
                i['uri'] = uri
                i['database'] = database
                i['channel'] = channel

                found.append(self.__call__(i))

            return found

        # look for medium based on its uri and the database it belongs to
        found = self._find(self.config, **current_file)

        if len(found) == 1:
            return found[0]

        elif len(found) == 0:
            uri = current_file['uri']
            msg = 'Could not find file "{uri}".'
            raise ValueError(msg.format(uri=uri))

        else:
            uri = current_file['uri']
            msg = 'Found {n} matches for file "{uri}"'
            raise ValueError(msg.format(uri=uri, n=len(found)))


def get_unique_identifier(item):
    """Return unique item identifier

    The complete format is {database}/{uri}_{channel}:
    * prefixed by "{database}/" only when `item` has a 'database' key.
    * suffixed by "_{channel}" only when `item` has a 'channel' key.

    Parameters
    ----------
    item : dict
        Item as yielded by pyannote.database protocols

    Returns
    -------
    identifier : str
        Unique item identifier
    """

    IDENTIFIER = ""

    # {database}/{uri}_{channel}
    if "database" in item:
        IDENTIFIER += "{database}/"
    IDENTIFIER += "{uri}"
    if "channel" in item:
        IDENTIFIER += "_{channel:d}"

    return IDENTIFIER.format(**item)


def get_annotated(current_file):

    # if protocol provides 'annotated' key, use it
    if 'annotated' in current_file:
        annotated = current_file['annotated']
        return annotated

    # if it does not, but does provide 'audio' key
    # try and use wav duration

    if 'audio' in current_file:
        try:
            from pyannote.audio.features.utils import get_audio_duration
            duration = get_audio_duration(current_file)
        except ImportError as e:
            pass
        else:
            warnings.warn('"annotated" was approximated by "audio" duration.')
            annotated = Timeline([Segment(0, duration)])
            return annotated

    warnings.warn('"annotated" was approximated by "annotation" extent.')
    extent = current_file['annotation'].get_timeline().extent()
    annotated = Timeline([extent])
    return annotated


def get_label_identifier(label, current_file):
    """Return unique label identifier

    Parameters
    ----------
    label : str
        Database-internal label
    current_file
        Yielded by pyannote.database protocols

    Returns
    -------
    unique_label : str
        Global label
    """

    # TODO. when the "true" name of a person is used,
    # do not preprend database name.
    database = current_file['database']
    return database + '|' + label
