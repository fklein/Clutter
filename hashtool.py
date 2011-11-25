#!/usr/bin/env python3

__author__ = "Florian Klein <fklein-at-lavabit-dot-com>"
__version__ = "0.2.0 alpha"
__doc__ = "A command-line tool for generating and verifying file hashes."

import hashlib
import sys
import argparse
import os
import time
import zlib
import abc
import fnmatch

class Console(object):
    """A wrapper for the print function that filters output according to a
    verbosity level.

    """
    QUIET = -1
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    FATAL = 50

    def __init__(self, level):
        """Initialize a new console."""
        self.level = level

    def write(self, level, *values, stream=sys.stdout):
        """Write a list of values to the console."""
        if self.level > 0 and level >= self.level:
            print(*values, file=stream)

    def debug(self, *values):
        """Debug a debug message."""
        self.write(Console.DEBUG, *values)

    def info(self, *values):
        """Write an info message."""
        self.write(Console.INFO, *values)

    def warning(self, *values):
        """Write a warning message."""
        self.write(Console.WARNING, *values)

    def error(self, *values):
        """Write an error message."""
        self.write(Console.ERROR, *values, stream=sys.stderr)

    def fatal(self, *values):
        """Write a fatal error message."""
        self.write(Console.FATAL, *values, stream=sys.stderr)

# Create a new global default console
console = Console(Console.DEBUG)


class _CRC32Hash(object):
    """Provides a hashlib-like interface to the CRC32 algorithm in
    the "zlib" module.

    """
    def __init__(self, data=None):
        """Initialize a new instance of the hash object."""
        self.name = 'crc32'
        self.block_size = 64
        self.digestsize = 4
        self.digest_size = self.digestsize
        self._datachunks = []
        if data:
            self.update(data)

    def update(self, data):
        """Update the digest with an additional string."""
        self._datachunks.append(data)

    def digest(self):
        """Return the current digest value."""
        crc32 = zlib.crc32("".join(self._datachunks))
        return "{0}".format(crc32)

    def hexdigest(self):
        """Return the current digest as a string of hexadecimal digits."""
        crc32 = zlib.crc32("".join(self._datachunks))
        return "{0:x}".format(crc32)


def _hash_factory(hash_name):
    """Return a hash object for the specified hash function."""
    if hash_name.lower() == 'crc32':
        return _CRC32Hash()
    else:
        return hashlib.new(hash_name)


class Filehash(object):
    """Calculate the hash of a file.

    The class supports all hash algorithms implemented by the
    local "hashlib" module, plus CRC32.

    """
    def __init__(self, hash_name, filename):
        h = _hash_factory(hash_name)
        with open(filename, 'r') as file:
            chunk = file.read(h.block_size)
            while chunk:
                h.update(chunk)
                chunk = file.read(h.block_size)
        self._hash = h
        self.hash_name = hash_name

    def hexdigest(self):
        """Return the files digest as a string of hexadecimal digits."""
        return self._hash.hexdigest()

    def digest(self):
        """Return the files digest value."""
        return self._hash.digest()


class GlobFilter(object):
    """Implement a filter based on a list of globs."""

    def __init__(self, include=[], exclude=[]):
        """Initialize the new filter object."""
        self.include = include
        self.exclude = exclude

    def __call__(self, string):
        """Filter an entry through the provided globs.

        Returns true if the entry should be included or false if it is to
        be excluded.

        """
        for glob in self.exclude:
            if fnmatch.fnmatch(string, glob):
                return False
        if not self.include:
            return True
        for glob in self.include:
            if fnmatch.fnmatch(string, glob):
                return True
        return False

    def filter(self, iterable):
        """Filter an iterable and return the result."""
        return filter(self, iterable)


class AbstractDirectoryCrawler(object, metaclass=abc.ABCMeta):
    """Provide basic functionality shared by all other directory crawlers."""

    def __init__(self, *, include, exclude):
        """Initialize the crawler."""
        self.include = include
        self.exclude = exclude

    def _write_checkfile(self, filename, hashinfo):
        """Write files hashes to a checksum file.

        The hashinfo has to be provided as a nested list or tuple :
        [(filename1, hash1), ..., (filenameN, hashN)]

        """
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(filename, 'w') as file:
            file.write("# Generated on {0}".format(ts) + os.linesep)
            for filepath, hash in hashinfo:
                file.write("{0} *{1}".format(hash, filepath) + os.linesep)

    def _read_checkfile(self, filename):
        """Parse and return the content of a checksum file.

        The return value is a nested tuple of the following format:
        ((filename1, hash1), ..., (filenameN, hashN))

        """
        hashinfo = []
        with open(filename, 'r') as file:
            for line in file:
                line = line.strip()
                if line.startswith('#'):
                    continue
                hash, _, filepath = line.partition(' *')
                if not hash:
                    hash, _, filepath = line.partition(' ')
                if hash and filepath:
                    hashinfo.append((filepath, hash))
        return tuple(hashinfo)

    @abc.abstractmethod
    def process_directory(self, root):
        """Crawl a directory and do what has to be done."""
        pass


class HashGenerator(AbstractDirectoryCrawler):
    """Generate checksum files for files in a directory tree.

    The object supports the following arguments:

        hash_name -- The name of a hash function. This can be any hash function
            supported by the hashlib module or 'crc32'.

        recursive -- Recursively process all subdirectories. Otherwise only the
            base directory is processed.

        basedir_only -- Only create a single checksum file inside the base
            directory. This will also contain the hashes of files within
            subdirectories (if recursion is enabled of course). Otherwise a
            distinct checksum file is created for each directory, which is also
            the default behaviour.

        filename -- The filename given to the created hashfiles. If this is not
            provided, a default ("checksums.<hashname>") is used. This option
            can be overridden by the "overwrite" argument.

        overwrite - A list of globs that specifies which files to overwrite.
            Overwrite any files matching one of the globs with the content of
            the generated checksum file. This can be used to replace existing
            checksum files with a new version. If this list is empty or no
            matching is found the filename specified in "filename" is used.

        backup -- Backup files that are being overwritten. Defaults to False.

        include -- A list of globs. Hashes will only be calculated and stored
            for files that match any of the globs in this list. If this list is
            empty, all files will be included (same as ['*']).

        exclude -- A list of globs. No hash is calculated for files matching
            any of the globs in this list. Exclude no file if this is empty.

        console -- The Console instance that all output will be sent to.

    Example:

        >>> g = HashGenerator('sha256', recursive=True, filename='dir.check',
                              include=['*'], exclude=['*.tmp', '*.bak'])
        >>> g.process_directory('/home/foo/bar')

    """
    def __init__(self, hash_name, *,
                 recursive=False, basedir_only=False, filename=None,
                 overwrite=[], backup=False, include=[], exclude=[]):
        """Initialize a new HashGenerator with the given options."""
        super(HashGenerator, self).__init__(include=include, exclude=exclude)
        self.hash_name = hash_name
        self.recursive = recursive
        self.basedir_only = basedir_only
        self.overwrite = overwrite
        self.backup = backup
        if filename:
            self.filename = filename
        else:
            self.filename = 'checksums' + '.' + hash_name

    def _write_hashinfo(self, directory, hashinfo):
        """Write files hashes to a directory.

        If an overwrite glob pattern is specified any matching files within the
        directory are overwritten with the hash information (possibly
        backing-up the original files). In case there are no files to be
        overwritten (i.e. no glob specified or no matching file found) the name
        of the hash file is taken from the 'filename' member.

        The hashinfo has to be provided as a list or tuple like this:

            [(filename1, hash1), ..., (filenameN, hashN)]

        """
        files_to_write = []

        for glob in self.overwrite:
            matching_items = fnmatch.filter(os.listdir(directory), glob)
            isfile = lambda name: os.path.isfile(os.path.join(directory, name))
            files_to_write.extend(filter(isfile, matching_items))
        if not files_to_write:
            files_to_write.append(self.filename)

        for file in files_to_write:
            filepath = os.path.join(directory, file)
            if os.path.exists(filepath) and self.backup:
                console.debug("Backing-up", filepath, "...")
                os.rename(filepath, filepath + '.bak')
            self._write_checkfile(filepath, hashinfo)
            console.info("Checksum file", filepath, "created ...")

    def process_directory(self, root):
        """Generate checksum file(s) for a directory."""
        dirtree = os.walk(root, topdown=True)
        if not self.recursive:
            dirtree = [next(dirtree), ]

        tree_hashes = []  # All hashes for files in the whole directory tree
        is_relevant = GlobFilter(include=self.include, exclude=self.exclude)
        for dir, subdirs, subfiles in dirtree:
            console.debug("Processing directory", dir, "...")
            dir_hashes = []  # All hashes for files in the current directory
            # Process all files as specified by "include" and "exclude"
            for file in filter(is_relevant, subfiles):
                filepath = os.path.join(dir, file)
                hash = Filehash(self.hash_name, filepath).hexdigest()
                console.debug(hash, "->", filepath)
                # Store the files hash for later use
                dir_hashes.append((file, hash))
                tree_hashes.append((os.path.relpath(filepath, root), hash))
            if dir_hashes and not self.basedir_only:
                self._write_hashinfo(dir, dir_hashes)
        if tree_hashes and self.basedir_only:
            self._write_hashinfo(root, tree_hashes)


class HashVerifier(AbstractDirectoryCrawler):
    """Search for checksum files inside a directory tree and verify them.

    The object supports the following arguments:

        hash_name -- The name of a hash function. This can be any hash function
            supported by the hashlib module or 'crc32'.

        recursive -- Recursively process all subdirectories. Otherwise only the
            base directory is processed.

        checkfiles -- A list of globs. Any files matching one of these globs
            will be regarded as checksum files and be verified. If this list is
            empty the default glob is "*.<hashname>".

        include -- A list of globs. Hashes will only be verified for files that
            match any of the globs in this list. If this list is empty, all
            files will be verified (same as ['*']). This argument can usually
            be skipped.

        exclude -- A list of globs. No hash is verified for files matching
            any of the globs in this list. Exclude no file if this is empty.
            This argument can usually be skipped.


        console -- The Console instance that all output will be sent to.

    Example:

        >>> v = HashVerifier('md5', recursive=True, checkfiles=['*.md5'],
                             include=['*'], exclude=['*.tmp', '*.bak'])
        >>> v.process_directory('/home/foo/bar')

    """
    def __init__(self, hash_name, *,
                 recursive=False, checkfiles=[], include=[], exclude=[]):
        """Initialize a new HashVerifier with the given options."""
        super(HashVerifier, self).__init__(include=include, exclude=exclude)
        self.hash_name = hash_name
        self.recursive = recursive
        if checkfiles:
            self.checkfiles = checkfiles
        else:
            self.checkfiles = ['*.' + hash_name, ]

    def process_directory(self, root) :
        dirtree = os.walk(root, topdown=True)
        if not self.recursive:
            dirtree = [next(dirtree), ]

        is_checkfile = GlobFilter(include=self.checkfiles)
        is_relevant = GlobFilter(include=self.include, exclude=self.exclude)
        for dir, subdirs, subfiles in dirtree:
            console.debug("Processing directory", dir, "...")
            for checkfile in filter(is_checkfile, subfiles):
                checkfile_ok = True
                checkfile_path = os.path.join(dir, checkfile)
                console.debug("Verifying file", checkfile_path, "...")
                hashinfo = self._read_checksum_file(checkfile_path)
                # Check each entry in the checksum file
                for hashfile, hash_stored in hashinfo:
                    hashfile_path = os.path.join(dir, hashfile)
                    if not is_relevant(os.path.basename(hashfile_path)):
                        # Skip verifying any unwanted files as specified by the
                        # include and exclude parameters.
                        console.debug("[SKIPPED]", hashfile_path)
                        continue
                    if not os.path.isfile(hashfile_path):
                        checkfile_ok = False
                        console.error("[MISSING]", hashfile_path)
                        continue
                    hash_now = Filehash(self.hash_name,
                                        hashfile_path).hexdigest()
                    if hash_now.lower() != hash_stored.lower():
                        checkfile_ok = False
                        console.error("[INVALID]", hashfile_path)
                    else:
                        console.debug("[OK]", hashfile_path)
                if not checkfile_ok:
                    console.error(checkfile_path, ": ERROR!")
                else:
                    console.info(checkfile_path, ": OK")


class UncheckedFileFinder(AbstractDirectoryCrawler):
    """Search for files that are not referenced in a checksum file.

    The object supports the following arguments:

        recursive -- Recursively process all subdirectories. Otherwise only the
            base directory is processed.

        checkfiles -- A list of globs. Any files matching one of these globs
            will be regarded as checksum files and be parsed. The arguement is
            mandatory.

        include -- A list of globs. Hashes will only be verified for files that
            match any of the globs in this list. If this list is empty, all
            files will be verified (same as ['*']). This argument can usually
            be skipped.

        exclude -- A list of globs. No hash is verified for files matching
            any of the globs in this list. Exclude no file if this is empty.
            This argument can usually be skipped.

        console -- The Console instance that all output will be sent to.

    Example:

        >>> u = UncheckedCrawler(checkfiles=['*.md5', 'check*.sfv'], 
                                 recursive=True, exclude=['*.tmp', '*.bak'])
        >>> u.process_directory('/home/foo/bar')

    """
    def __init__(self, *,
                 checkfiles, recursive=False, include=None, exclude=None):
        """Initialize a new UncheckedCrawler with the given options."""
        super(UncheckedCrawler, self).__init__(include=include,
                                               exclude=exclude)
        self.recursive = recursive
        self.checkfiles = checkfiles

    def process_directory(self, root) :
        dirtree = os.walk(root, topdown=True)
        if not self.recursive:
            dirtree = [next(dirtree), ]

        hashed_files = []
        is_checkfile = GlobFilter(include=self.checkfiles)
        is_relevant = GlobFilter(include=self.include, exclude=self.exclude)
        for dir, subdirs, subfiles in dirtree:
            console.debug("Processing directory", dir, "...")
            # Find all checksum files in the current directory and add all
            # file they contain to the "hashed_files" list.
            for checkfile in filter(is_checkfile, subfiles):
                checkfile_path = os.path.join(dir, checkfile)
                console.debug("Reading file", checkfile_path, "...")
                hashinfo = self._read_hashfile(checkfile_path)
                for file, _ in hashinfo:
                    hashed_files.append(os.path.join(dir, file))
            # Find all relevant files in the current directory and check if any
            # checksum file contained a hash for the file.
            for file in filter(is_relevant, subfiles):
                filepath = os.path.join(dir, file)
                if filepath not in hashed_files:
                    console.warning("[UNCHECKED]", filepath)
                else:
                    console.debug("[OK]", filepath)


def parse_arguments():
    valid_hash_functions = (
        'md5', 'sha1', 'sha224', 'sha256', 'sha384', 'sha512', 'crc32'
    )

    # The arguments of the base parser
    root_parser_arguments = (
        ('-v', '--verbose',
            {'dest': 'verbose',
             'action': 'store_true',
             'help': """Be chatty and print verbose information."""}),
        ('-d', '--debug',
            {'dest': 'debug',
             'action': 'store_true',
             'help': """Be very chatty and print debug information."""}),
        ('-q', '--quiet',
            {'dest': 'quiet',
             'action': 'store_true',
             'help': """Supress all output except error messages."""}),
        ('--version',
            {'action': 'version',
             'version': __version__,
             'help': """Print version information and exit."""})
    )

    # The arguments of the "generate" subparser
    generate_parser_arguments = (
        ('hash_name',
            {'choices': valid_hash_functions,
             'metavar': 'HASHNAME',
             'help': """The hash function to be used."""}),
        ('-r', '--recursive',
            {'dest': 'recursive',
             'action': 'store_true',
             'help': """Recursively process any subdirectories."""}),
        ('-b', '--basedir',
            {'dest': 'basedir_only',
             'action': 'store_true',
             'help': """Create only one single checksum file in the base
                     directory. Otherwise the default is to create a distinct
                     checksum file for each directory. This option is only
                     meaningful if recursion is enabled."""}),
        ('-f', '--filename',
            {'dest': 'filename',
             'metavar': 'NAME',
             'help': """The filename given to the created checksum files.
                     This can be overridden by the "--overwrite" argument.
                     If this argument is missing, the default value
                     "checksums.<hashname>" (e.g. "checksums.sha256") is
                     used."""}),
        ('-o', '--overwrite',
            {'dest': 'overwrite_globs',
             'action': 'append',
             'metavar': 'GLOB',
             'help': """Overwrite any files matching this glob with the content
                     of the generated checksum file. This can be used to
                     replace existing checksum files with a new version.
                     If this argument is missing or no matching file is found
                     the value specified in "--filename" is used."""}),
        ('-n', '--no-backup',
            {'dest': 'backup',
             'action': 'store_false',
             'help': """Do not back up files before overwriting them."""}),
        ('-i', '--include',
            {'dest': 'include_globs',
             'action': 'append',
             'metavar': 'GLOB',
             'help': """Only store a files hash if the filename matches this
                     glob. This may be supplied multiple times. If this is not
                     specified include all files (same behaviour as
                     --include "*")."""}),
        ('-e', '--exclude',
            {'dest': 'exclude_globs',
             'action': 'append',
             'metavar': 'GLOB',
             'help': """Do not store a files hash if the filename matches this
                     glob. This may be supplied multiple times."""}),
        ("directories",
            {'nargs': '+',
             'metavar': 'DIRECTORY',
             'help': """The directory to process."""})
    )

    # The arguments of the "verify" subparser
    verify_parser_arguments = (
        ('hash_name',
            {'choices': valid_hash_functions,
             'metavar': 'HASHNAME',
             'help': """The hash function to be used."""}),
        ('-r', '--recursive',
            {'dest': 'recursive',
             'action': 'store_true',
             'help': """Recursively process any subdirectories."""}),
        ('-f', '--filename',
            {'dest': 'filename_globs',
             'action': 'append',
             'metavar': 'GLOB',
             'help': """Treat any file matching this glob as a checksum file
                     and attempt to verify it. This may be supplied multiple
                     times. If this argument is missing, the default value
                     "*.<hashname>" (e.g. "*.sha256") is used."""}),
        ('-i', '--include',
            {'dest': 'include_globs',
             'action': 'append',
             'metavar': 'GLOB',
             'help': """Only verify a files hash if the filename matches this
                     glob. This may be supplied multiple times. If this is not
                     specified all files will be verified (same behaviour
                     as --include "*")."""}),
        ('-e', '--exclude',
            {'dest': 'exclude_globs',
             'action': 'append',
             'metavar': 'GLOB',
             'help': """Do not verify a files hash if the filename matches this
                     glob. This may be supplied multiple times."""}),
        ('directories',
            {'nargs': '+',
             'metavar': 'DIRECTORY',
             'help': """The directory to process."""})
    )

    # The arguments of the "unchecked" subparser
    unchecked_parser_arguments = (
        ('-r', '--recursive',
            {'dest': 'recursive',
             'action': 'store_true',
             'help': """Recursively process any subdirectories."""}),
        ('-f', '--filename',
            {'dest': 'filename_globs',
             'action': 'append',
             'required': True,
             'metavar': 'GLOB',
             'help': """Treat any file matching this glob as a checksum file
                     and attempt to parse it. This may be supplied multiple
                     times."""}),
        ('-i', '--include',
            {'dest': 'include_globs',
             'action': 'append',
             'metavar': 'GLOB',
             'help': """Only warn about files if the filename matches this
                     glob. This may be supplied multiple times. If this is not
                     specified all files with no hash will be reported (same
                     behaviour as --include "*")."""}),
        ('-e', '--exclude',
            {'dest': 'exclude_globs',
             'action': 'append',
             'metavar': 'GLOB',
             'help': """Do not warn about files if the filename matches this
                     glob. This may be supplied multiple times."""}),
        ('directories',
            {'nargs': '+',
             'metavar': 'DIRECTORY',
             'help': """The directory to process."""})
    )

    # Create the root parser with the arguments defined above.
    root_parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="(c) {}".format(__author__))
    for *flags, kwargs in root_parser_arguments:
        root_parser.add_argument(*flags, **kwargs)

    # Create the subparsers with the arguments defined above.
    subparsers = root_parser.add_subparsers(
        dest='operation',
        help='Specifies what task to perform')

    help_text = """Scan a directory for files, calculate a hash for each file
                and store it in a checksum file."""
    generate_parser = subparsers.add_parser('generate', help=help_text)
    for *flags, kwargs in generate_parser_arguments:
        generate_parser.add_argument(*flags, **kwargs)

    help_text = """Scan a directory for checksum files and verify the hashes
                within these files."""
    verify_parser = subparsers.add_parser('verify', help=help_text)
    for *flags, kwargs in verify_parser_arguments:
        verify_parser.add_argument(*flags, **kwargs)

    help_text = """Scan a directory for files that are not included in a
                checksum file."""
    unchecked_parser = subparsers.add_parser('unchecked', help=help_text)
    for *flags, kwargs in unchecked_parser_arguments:
        unchecked_parser.add_argument(*flags, **kwargs)

    # Parse and return the command-line arguments
    return root_parser.parse_args()


def hashtool():
    """Parse the command-line options and run the requested operation."""
    args = parse_arguments()
    # print(args)

    console.level = Console.WARNING
    if args.verbose:
        console.level = Console.INFO
    if args.debug:
        console.level = Console.DEBUG
    if args.quiet:
        console.level = Console.QUIET

    if args.operation == 'generate':
        crawler = HashGenerator(args.hash_name,
                                recursive=args.recursive,
                                basedir_only=args.basedir_only,
                                filename=args.filename,
                                overwrite=args.overwrite_globs,
                                backup=args.backup,
                                include=args.include_globs,
                                exclude=args.exclude_globs)
    elif args.operation == 'verify':
        crawler = HashVerifier(args.hash_name,
                               recursive=args.recursive,
                               checkfiles=args.filename_globs,
                               include=args.include_globs,
                               exclude=args.exclude_globs)
    elif args.operation == 'unchecked':
        crawler = UncheckedFileFinder(recursive=args.recursive,
                                      checkfiles=args.filename_globs,
                                      include=args.include_globs,
                                      exclude=args.exclude_globs)
    else:
        raise ValueError('Unknown operation: {}'.format(args.operation))

    for directory in args.directories:
        crawler.process_directory(directory)


if __name__ == '__main__':
    hashtool()
