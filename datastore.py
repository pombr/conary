#
# Copyright (c) 2004 Specifix, Inc.
# All rights reserved
#

"""
Provides a data storage mechanism for files which are indexed by a hash
index.

The hash can be any arbitrary string of at least 5 bytes in length;
keys are assumed to be unique.
"""

import fcntl
import gzip
import os
import struct
import util

class DataStore:

    def hashToPath(self, hash):
	if (len(hash) < 5):
	    raise KeyError, ("invalid hash %s" % hash)

	dir = os.sep.join((self.top, hash[0:2], hash[2:4]))
	name = os.sep.join((dir, hash[4:]))
	return (dir, name)

    def hasFile(self, hash):
	path = self.hashToPath(hash)[1]
	return os.path.exists(path)

    def decrementCount(self, path):
	"""
	Decrements the count by one; it it becomes 1, the count file
	is removed. If it becomes zero, the contents are removed.
	"""
        countPath = path + "#"

	# use the count file for locking, *even if it doesn't exist*
	countFile = os.open(countPath, os.O_RDWR | os.O_CREAT)
	fcntl.lockf(countFile, fcntl.LOCK_EX)

	val = os.read(countFile, 100)
	if not val:
	    # no count file, remove the file
	    os.unlink(path)
	    # someone may try to recreate the file in here, but it should
	    # work fine. even if multiple processes try to, one will create
	    # the file and the rest will block on the countFile. once
	    # we unlink it, everything will get moving again.
	    os.unlink(countPath)
	else:
	    val = int(val[:-1])
	    if val == 1:
		os.unlink(countPath)
	    else:
		val -= 1
		os.lseek(countFile, 0, 0)
		os.ftruncate(countFile, 0)
		os.write(countFile, "%d\n" % val)

	os.close(countFile)

    def incrementCount(self, path, fileObj = None):
	"""
	Increments the count by one.  it becomes one, the contents
	of fileObj are stored into that path.
	"""
        countPath = path + "#"

	if os.path.exists(path):
	    # if the path exists, it must be correct since we move the
	    # contents into place atomicly. all we need to do is
	    # increment the count
	    countFile = os.open(countPath, os.O_RDWR | os.O_CREAT)
	    fcntl.lockf(countFile, fcntl.LOCK_EX)

	    val = os.read(countFile, 100)
	    if not val:
		val = 0
	    else:
		val = int(val[:-1])

	    val += 1
	    os.lseek(countFile, 0, 0)
	    os.ftruncate(countFile, 0)
	    os.write(countFile, "%d\n" % val)
	    os.close(countFile)
	else:
	    # new file, try to be the one who creates it
	    newPath = path + ".new"

	    fd = os.open(newPath, os.O_RDWR | os.O_CREAT)

	    # get a write lock on the file
	    fcntl.lockf(fd, fcntl.LOCK_EX)

	    # if the .new file doesn't exist anymore, someone else must
	    # have gotten the write lock before we did, created the
	    # file, and then moved it into place. when this happens
	    # we need to update the count instead
	    
	    if not os.path.exists(newPath):
		os.close(fd)
		return self.incrementCount(path, fileObj = fileObj)

	    fObj = os.fdopen(fd, "r+")
	    dest = gzip.GzipFile(mode = "w", fileobj = fObj)
	    util.copyfileobj(fileObj, dest)
	    os.rename(newPath, path)

	    dest.close()
	    # this closes fd for us
	    fObj.close()

    def readCount(self, path):
        # XXX this code is not used anymore
	if os.path.exists(path + "#"):
	    fd = os.open(path + "#", os.O_RDONLY)
            fcntl.lockf(fd, fcntl.LOCK_SH)
            f = os.fdopen(fd)
	    # cut off the trailing \n
	    count = int(f.read()[:-1])
            os.close(fd)
	elif os.path.exists(path):
	    count = 1
	else:
	    count = 0

	return count

    # add one to the reference count for a file which already exists
    # in the archive
    def addFileReference(self, hash):
	(dir, path) = self.hashToPath(hash)
	self.incrementCount(path)
	return

    # file should be a python file object seek'd to the beginning
    # this messes up the file pointer
    def addFile(self, f, hash):
	(dir, path) = self.hashToPath(hash)

	shortPath = dir[:-3]

	if not os.path.exists(shortPath):
	    os.mkdir(shortPath)
	if not os.path.exists(dir):
	    os.mkdir(dir)

	self.incrementCount(path, fileObj = f)

    # returns a python file object for the file requested
    def openFile(self, hash, mode = "r"):
	path = self.hashToPath(hash)[1]
	f = open(path, "r")

	# read in the size of the file
	f.seek(-4, 2)
	size = f.read(4)
	f.seek(0)

	# we need the size to create a file container to pass over
	# the wire for getFileContents()
	size = struct.unpack("<i", size)[0]
	gzfile = gzip.GzipFile(path, mode)
	gzfile.fullSize = size
	return gzfile

    def removeFile(self, hash):
	(dir, path) = self.hashToPath(hash)
	self.decrementCount(path)

	try:
	    os.rmdir(dir)
	except OSError:
	    # if this fails there are probably just other files
	    # in that directory; just ignore it
	    pass

    def __init__(self, topPath):
	self.top = topPath
	if (not os.path.isdir(self.top)):
	    raise IOError, ("path is not a directory: %s" % topPath)
