#
# Copyright (c) 2005 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any waranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

import os
import sha
import md5
import StringIO
from Crypto.Cipher import AES
from Crypto.Cipher import DES3
from Crypto.Cipher import Blowfish
from Crypto.Cipher import CAST
from Crypto.PublicKey import RSA
from Crypto.PublicKey import DSA
from string import upper

# key types defined in RFC 2440 page 49
PK_ALGO_RSA                  = 1
PK_ALGO_RSA_ENCRYPT_ONLY     = 2  # deprecated
PK_ALGO_RSA_SIGN_ONLY        = 3  # deprecated
PK_ALGO_ELGAMAL_ENCRYPT_ONLY = 16
PK_ALGO_DSA                  = 17
PK_ALGO_ELLIPTIC_CURVE       = 18
PK_ALGO_ECDSA                = 19
PK_ALGO_ELGAMAL              = 20

PK_ALGO_ALL_RSA = (PK_ALGO_RSA, PK_ALGO_RSA_ENCRYPT_ONLY,
                   PK_ALGO_RSA_SIGN_ONLY)
PK_ALGO_ALL_ELGAMAL = (PK_ALGO_ELGAMAL_ENCRYPT_ONLY, PK_ALGO_ELGAMAL)

# packet tags are defined in RFC 2440 pages 15-16
PKT_TAG_RESERVED           = 0  # a packet tag must not have this value
PKT_TAG_PUB_SESSION_KEY    = 1  # Public-Key Encrypted Session Key Packet
PKT_TAG_SIG                = 2  # Signature Packet
PKT_TAG_SYM_SESSION_KEY    = 3  # Symmetric-Key Encrypted Session Key Packet
PKT_TAG_ONE_PASS_SIG       = 4  # One-Pass Signature Packet
PKT_TAG_SECRET_KEY         = 5  # Secret Key Packet
PKT_TAG_PUBLIC_KEY         = 6  # Public Key Packet
PKT_TAG_SECRET_SUBKEY      = 7  # Secret Subkey Packet
PKT_TAG_COMPRESSED_DATA    = 8  # Compressed Data Packet
PKT_TAG_SYM_ENCRYPTED_DATA = 9  # Symmetrically Encrypted Data Packet
PKT_TAG_MARKER             = 10 # Marker Packet
PKT_TAG_LITERAL_DATA       = 11 # Literal Data Packet
PKT_TAG_TRUST              = 12 # Trust Packet
PKT_TAG_USERID             = 13 # User ID Packet
PKT_TAG_PUBLIC_SUBKEY      = 14 # Public Subkey Packet
PKT_TAG_PRIVATE1           = 60 # 60 to 63 -- Private or Experimental Values
PKT_TAG_PRIVATE2           = 61
PKT_TAG_PRIVATE3           = 62
PKT_TAG_PRIVATE4           = 63

PKT_TAG_ALL_SECRET = (PKT_TAG_SECRET_KEY, PKT_TAG_SECRET_SUBKEY)
PKT_TAG_ALL_PUBLIC = (PKT_TAG_PUBLIC_KEY, PKT_TAG_PUBLIC_SUBKEY)
PKT_TAG_ALL_KEYS = PKT_TAG_ALL_SECRET + PKT_TAG_ALL_PUBLIC

# 3.6.2.1. Secret key encryption
ENCRYPTION_TYPE_UNENCRYPTED    = 0x00
ENCRYPTION_TYPE_S2K_SPECIFIED  = 0xff
# GPG man page hints at existence of "sha cehcksum" and claims it
#     will be part of "the new forthcoming extended openpgp specs"
#     for now: experimentally determined to be 0xFE
ENCRYPTION_TYPE_SHA1_CHECK = 0xfe

SEEK_SET = 0
SEEK_CUR = 1
SEEK_END = 2

class MalformedKeyRing(Exception):
    def __str__(self):
        return self.error

    def __init__(self, reason="Malformed Key Ring"):
        self.error = "Malformed Key Ring: %s" %reason

class IncompatibleKey(Exception):
    def __str__(self):
        return self.error

    def __init__(self, reason="Incompatible Key"):
        self.error = "Incompatible Key: %s" %reason

class KeyNotFound(Exception):
    def __str__(self):
        return self.error

    def __init__(self, keyId, reason=None):
        if keyId:
            self.error = "OpenPGP key not found for key ID %s" %keyId
        else:
            self.error = "No OpenPGP keys found"
        if reason:
            self.error += ': %s' %reason

class BadPassPhrase(Exception):
    def __str__(self):
        return self.error

    def __init__(self, reason="Bad passphrase"):
        self.error = reason

def getBlockType(keyRing):
    r=keyRing.read(1)
    if r != '':
        return ord(r)
    else:
        return -1

def convertPrivateKey(privateBlock):
    if not len(privateBlock):
        return ''
    packetType = ord(privateBlock[0])
    if not (packetType & 128):
        raise MalformedKeyRing("Not an OpenPGP packet.")
    if packetType & 64:
        return ''
    if ((packetType >> 2) & 15) in PKT_TAG_ALL_PUBLIC:
        return privateBlock
    if ((packetType >> 2) & 15) not in PKT_TAG_ALL_SECRET:
        return ''
    blockSize=0
    if ((packetType >> 2) & 15) == PKT_TAG_SECRET_KEY:
        newPacketType = 0x98
    else:
        newPacketType = 0xb8
    if not (packetType & 3):
        index = 2
    elif (packetType & 3) == PKT_TAG_PUB_SESSION_KEY:
        index = 3
    elif (packetType & 3) == PKT_TAG_SIG:
        index = 5
    else:
        raise MalformedKeyRing("Packet of indeterminate size.")
    if ord(privateBlock[index]) != 4:
        return ''
    buf = privateBlock[index:index + 6]
    index += 5
    algType = ord(privateBlock[index])
    index += 1
    if algType in PK_ALGO_ALL_RSA:
        numMPI = 2
    elif algType in PK_ALGO_ALL_ELGAMAL:
        numMPI = 3
    elif algType == PK_ALGO_DSA:
        numMPI = 4
    else:
        return ''
    for i in range(0, numMPI):
        mLen = ((ord(privateBlock[index]) * 256 +
                 ord(privateBlock[index + 1])) + 7) / 8 + 2
        buf = buf + privateBlock[index:index + mLen]
        index += mLen
    bufLen = len(buf)
    if bufLen > 65535:
        newPacketType |= 2
        sizeBytes = 4
    elif bufLen > 255:
        newPacketType |= 1
        sizeBytes = 2
    else:
        sizeBytes = 1
    sizeBuf=''
    for i in range(1, sizeBytes + 1):
        sizeBuf += chr((bufLen >> ((sizeBytes - i) << 3)) & 0xff)
    return (chr(newPacketType) + sizeBuf + buf)

def getKeyId(keyRing):
    keyBlock=getBlockType(keyRing)
    if not (keyBlock & 128):
        raise MalformedKeyRing("Not an OpenPGP packet.")

    if ((keyBlock == -1) or (keyBlock & 64)
        or (((keyBlock >> 2) & 15) not in PKT_TAG_ALL_KEYS)):
        return ''

    # RFC 2440 4.2.1 - Old-Format Packet Lengths
    if (keyBlock & 3) == 2:
        # Four-Octet length is 5 octets long
        dataSize = (ord(keyRing.read(1)) * (1 << 24) +
                    ord(keyRing.read(1)) * (1 << 16) +
                    ord(keyRing.read(1)) * (1 << 8) +
                    ord(keyRing.read(1)) + 5)
        keyRing.seek(-5, SEEK_CUR)
    elif (keyBlock & 3) == 1:
        # Two-Octet length is 3 octets long
        dataSize = ord(keyRing.read(1)) * (1 << 8) + ord(keyRing.read(1)) + 3
        keyRing.seek(-3, SEEK_CUR)
    elif (keyBlock & 3) == 0:
        # One-Octet length is 2 octets long
        dataSize = ord(keyRing.read(1)) + 2
        keyRing.seek(-2, SEEK_CUR)
    else:
        # We're unable to handle a packet length of indeterminate size
        raise MalformedKeyRing("Can't parse key of indeterminate size.")
    # read the data
    data = keyRing.read(dataSize)
    # move the current posititon back to the beginning of the data
    keyRing.seek(-1 * dataSize, SEEK_CUR)

    # handle private keys
    if ((keyBlock >> 2) & 15) in PKT_TAG_ALL_SECRET:
        data = convertPrivateKey(data)
    # This is a holdover from the days of PGP 2.6.2
    # RFC 2440 section 11.2 does a really bad job of explaining this
    # One of the least documented gotchas of Key fingerprints:
    # they're ALWAYS calculated as if they were a public key main key block.
    # this means private keys will be treated as public keys, and subkeys
    # will be treated as main keys for the purposes of this test.
    # Furthermore if the length was one byte long it must be translated
    # into a 2 byte long length (upper octet is 0)
    # not doing this will result in key fingerprints which do not match the
    # output produced by OpenPGP compliant programs.
    # this will result in the first octet ALWYAS being 0x99
    # in binary 10 0110 01
    # 10 indicates old style PGP packet
    # 0110 indicates public key
    # 01 indicates 2 bytes length
    keyBlock = ord(data[0])
    # Translate 1 byte length blocks to two byte length blocks
    if not (keyBlock & 1):
        data = chr(keyBlock|1) + chr(0) + data[1:]
    # promote subkeys to main keys
    # 0xB9 is the packet tag for a public subkey with two byte length
    # 0x9D is the packet tag for a private subkey with two byte length
    # 0x9D is a catchall at this point in the code. key data should already
    # be a public key
    if keyBlock in (0xb9, 0x9d):
        data = chr(0x99) + data[1:]
    m = sha.new()
    m.update(data)
    return m.hexdigest().upper()

# find the next PGP packet regardless of type.
def seekNextPacket(keyRing):
    packetType=getBlockType(keyRing)
    if packetType == -1:
        return
    dataSize = -1
    if not packetType & 64:
        # RFC 2440 4.2.1 - Old-Format Packet Lengths
        if not (packetType & 3):
            sizeLen = 1
        elif (packetType & 3) == 1:
            sizeLen = 2
        elif (packetType & 3) == 2:
            sizeLen = 4
        else:
            raise MalformedKeyRing("Can't seek past packet of indeterminate length.")
    else:
        # RFC 2440 4.2.2 - New-Format Packet Lengths
        octet=ord(keyRing.read(1))
        if octet < 192:
            sizeLen=1
            keyRing.seek(-1, SEEK_CUR)
        elif octet < 224:
            dataSize = (ord(keyRing.read(1)) - 192 ) * 256 + \
                       ord(keyRing.read(1)) + 192
        elif octet < 255:
            dataSize = 1 << (ord(keyRing.read(1)) & 0x1f)
        else:
            sizeLen=4
    # if we have not already calculated datasize, calculate it now
    if dataSize == -1:
        dataSize = 0
        for i in range(0, sizeLen):
            dataSize = (dataSize * 256) + ord(keyRing.read(1))
    keyRing.seek(dataSize, SEEK_CUR)

def seekNextKey(keyRing):
    done = 0
    while not done:
        seekNextPacket(keyRing)
        packetType = getBlockType(keyRing)
        if packetType != -1:
            keyRing.seek(-1, SEEK_CUR)
        if ((packetType == -1)
            or ((not (packetType & 64))
                and (((packetType >> 2) & 15) in PKT_TAG_ALL_KEYS))):
            done = 1

def seekNextSignature(keyRing):
    done = 0
    while not done:
        seekNextPacket(keyRing)
        packetType = getBlockType(keyRing)
        if packetType != -1:
            keyRing.seek(-1,SEEK_CUR)
        if ((packetType == -1)
            or ((not (packetType&64))
                and (((packetType >> 2) & 15) == PKT_TAG_SIG))):
            done = 1

def fingerprintToInternalKeyId(fingerprint):
    data = int(fingerprint[-16:],16)
    r = ''
    while data:
        r = chr(data%256) + r
        data /= 256
    return r

def getSigId(keyRing):
    startPoint = keyRing.tell()
    blockType = getBlockType(keyRing)
    lenBits = blockType & 3
    if lenBits == 3:
        raise MalformedKeyRing("Can't seek past packet of indeterminate length.")
    elif lenBits == 2:
        keyRing.seek(4, SEEK_CUR)
    else:
        keyRing.seek(lenBits+1, SEEK_CUR)
    assert (ord(keyRing.read(1)) == 4)
    keyRing.seek(3, SEEK_CUR)
    hashedLen = ord(keyRing.read(1)) * 256 + ord(keyRing.read(1))
    # hashedLen plus two to skip len of unhashed data.
    keyRing.seek(hashedLen + 2, SEEK_CUR)
    done = 0
    while not done:
        subLen = ord(keyRing.read(1))
        if ord(keyRing.read(1)) == 16:
            done = 1
    data = keyRing.read(subLen - 1)
    keyRing.seek(startPoint)
    return data

def assertSigningKey(keyId,keyRing):
    startPoint = keyRing.tell()
    keyRing.seek(0, SEEK_END)
    limit = keyRing.tell()
    if limit == 0:
        # no keys in a zero length file
        raise KeyNotFound(keyId, "Couldn't open keyring")
    keyRing.seek(0, SEEK_SET)
    while (keyRing.tell() < limit) and (keyId not in getKeyId(keyRing)):
        seekNextKey(keyRing)
    if keyRing.tell() >= limit:
        raise KeyNotFound(keyId)
    # keyring now points to the beginning of the key we wanted
    # find self signature of this key
    # FIXME: ensure we don't wander outside of this key...
    fingerprint = getKeyId(keyRing)
    intKeyId = fingerprintToInternalKeyId(fingerprint)
    seekNextSignature(keyRing)
    while (intKeyId != getSigId(keyRing)):
        seekNextSignature(keyRing)
    # we now point to the self signature.
    # now go find the Key Flags subpacket
    blockType = getBlockType(keyRing)
    lenBits = blockType & 3
    if lenBits == 3:
        raise MalformedKeyRing("Can't seek past packet of indeterminate length.")
    elif lenBits == 2:
        keyRing.seek(4, SEEK_CUR)
    else:
        keyRing.seek(lenBits+1, SEEK_CUR)
    assert (ord(keyRing.read(1)) == 4)
    keyRing.seek(5, SEEK_CUR)
    done = 0
    while not done:
        subLen = ord(keyRing.read(1))
        subType = ord(keyRing.read(1))
        if (subType != 27):
            keyRing.seek(subLen - 1, SEEK_CUR)
        else:
            done = 1
    Flags = ord(keyRing.read(1))
    if not (Flags & 2):
        raise InvalidKey('Key %s is not a signing key.'% fingerprint)
    keyRing.seek(startPoint)

def simpleS2K(passPhrase, hash, keySize):
    # RFC 2440 3.6.1.1.
    r = ''
    iteration = 0
    keyLength = ((keySize + 7) / 8)
    while len(r) < keyLength:
        d = hash.new(chr(0) * iteration)
        d.update(passPhrase)
        r += d.digest()
        iteration += 1
    return r[:keyLength]

def saltedS2K(passPhrase, hash, keySize, salt):
    # RFC 2440 3.6.1.2.
    r = ''
    iteration = 0
    keyLength = ((keySize + 7) / 8)
    while(len(r) < keyLength):
        d = hash.new()
        buf = chr(0) * iteration
        buf += salt + passPhrase
        d.update(buf)
        r += d.digest()
        iteration += 1
    return r[:keyLength]

def iteratedS2K(passPhrase, hash, keySize, salt, count):
    # RFC 2440 3.6.1.3.
    r=''
    iteration = 0
    count=(16 + (count & 15)) << ((count >> 4) + 6)
    buf = salt + passPhrase
    keyLength = (keySize + 7) / 8
    while(len(r) < keyLength):
        d = hash.new()
        d.update(iteration * chr(0))
        total = 0
        while (count - total) > len(buf):
            d.update(buf)
            total += len(buf)
        if total:
            d.update(buf[:count-total])
        else:
            d.update(buf)
        r += d.digest()
        iteration += 1
    return r[:keyLength]

def readMPI(keyRing):
    MPIlen=(ord(keyRing.read(1)) * 256 + ord(keyRing.read(1)) + 7 ) / 8
    r=0L
    for i in range(0,MPIlen):
        r = r * 256 + ord(keyRing.read(1))
    return r

def readBlockSize(keyRing, sizeType):
    if not sizeType:
        return ord(keyRing.read(1))
    elif sizeType == 1:
        return ord(keyRing.read(1)) * 256 + ord(keyRing.read(1))
    elif sizeType == 2:
        return (ord(keyRing.read(1)) * 0x1000000 +
                ord(keyRing.read(1)) * 0x10000 +
                ord(keyRing.read(1)) * 0x100 +
                ord(keyRing.read(1)))
    else:
        raise MalformedKeyRing("Can't get size of packet of indeterminate length")

def getGPGKeyTuple(keyId, keyRing, secret=0, passPhrase=''):
    keyRing.seek(0, SEEK_END)
    limit = keyRing.tell()
    if limit == 0:
        # empty file, there can be no keys in it
        raise KeyNotFound(keyId)
    if secret:
        assertSigningKey(keyId, keyRing)
    keyRing.seek(0)
    while (keyId not in getKeyId(keyRing)):
        seekNextKey(keyRing)
        if keyRing.tell() == limit:
            raise KeyNotFound(keyId)
    startLoc=keyRing.tell()
    packetType=ord(keyRing.read(1))
    if secret and (not ((packetType>>2) & 1)):
        raise IncompatibleKey("Can't get private key from public keyring!")
    limit = (readBlockSize(keyRing, packetType & 3) +
             (packetType & 3) + 1 + startLoc)
    if ord(keyRing.read(1)) != 4:
        raise MalformedKeyRing("Can only read V4 packets")
    keyRing.seek(4, SEEK_CUR)
    keyType = ord(keyRing.read(1))
    if keyType in PK_ALGO_ALL_RSA:
        # do RSA stuff
        # n e
        n = readMPI(keyRing)
        e = readMPI(keyRing)
        if secret:
            privateMPIs = decryptPrivateKey(keyRing, limit, 4, passPhrase)
            r = (n, e, privateMPIs[0], privateMPIs[1],
                 privateMPIs[2], privateMPIs[3])
        else:
            r = (n, e)
    elif keyType in (PK_ALGO_DSA,):
        p = readMPI(keyRing)
        q = readMPI(keyRing)
        g = readMPI(keyRing)
        y = readMPI(keyRing)
        if secret:
            privateMPIs=decryptPrivateKey(keyRing, limit, 1, passPhrase)
            r = (y, g, p, q, privateMPIs[0])
        else:
            r = (y, g, p, q)
    elif keyType in PK_ALGO_ALL_ELGAMAL:
        raise MalformedKeyRing("Can't use El-Gamal keys in current version")
        p = readMPI(keyRing)
        g = readMPI(keyRing)
        y = readMPI(keyRing)
        if secret:
            privateMPIs = decryptPrivateKey(keyRing, limit, 1, passPhrase)
            r = (y, g, p, privateMPIs[0])
        else:
            r = (p, g, y)
    else:
        raise MalformedKeyRing("Wrong key type")
    keyRing.close()
    return r

def makeKey(keyTuple):
    # public lengths: rsa=2, dsa=4, elgamal=3
    # private lengths: rsa=6 dsa=5 elgamal=4
    if len(keyTuple) in (2, 6):
        return RSA.construct(keyTuple)
    if len(keyTuple) in (4, 5):
        return DSA.construct(keyTuple)

def getPublicKey(keyId, keyFile=''):
    if keyFile == '':
        if 'HOME' not in os.environ:
            keyFile = None
        else:
            keyFile=os.environ['HOME'] + '/.gnupg/pubring.gpg'
    try:
        keyRing=open(keyFile)
    except IOError:
        raise KeyNotFound(keyId, "Couldn't open pgp keyring")
    key = makeKey(getGPGKeyTuple(keyId, keyRing, 0, ''))
    keyRing.close()
    return key

def getPrivateKey(keyId,passPhrase='', keyFile=''):
    if keyFile == '':
        if 'HOME' not in os.environ:
            keyFile = None
        else:
            keyFile=os.environ['HOME'] + '/.gnupg/secring.gpg'
    try:
        keyRing=open(keyFile)
    except IOError:
        raise KeyNotFound(keyId, "Couldn't open pgp keyring")
    key =  makeKey(getGPGKeyTuple(keyId, keyRing, 1, passPhrase))
    keyRing.close()
    return key

def getDBKey(keyId, keyTable):
    keyData = keyTable.getPGPKeyData(keyId)
    keyRing = StringIO.StringIO(keyData)
    key = makeKey(getGPGKeyTuple(keyId, keyRing, 0, ''))
    keyRing.close()
    return key

def getFingerprint(keyId, keyFile=''):
    if keyFile == '':
        if 'HOME' not in os.environ:
            keyFile = None
        else:
            keyFile=os.environ['HOME'] + '/.gnupg/pubring.gpg'
    try:
        keyRing=open(keyFile)
    except IOError:
        raise KeyNotFound(keyId, "Couldn't open keyring")
    keyRing.seek(0, SEEK_END)
    limit = keyRing.tell()
    if limit == 0:
        # no keys in a zero length file
        raise KeyNotFound(keyId, "Couldn't open keyring")
    keyRing.seek(0, SEEK_SET)
    while (keyRing.tell() < limit) and (keyId not in getKeyId(keyRing)):
        seekNextKey(keyRing)
    if keyRing.tell() >= limit:
        raise KeyNotFound(keyId)
    return getKeyId(keyRing)

def verifyRFC2440Checksum(data):
    # RFC 2440 5.5.3 - Secret Key Packet Formats documents the checksum
    if len(data) < 2:
        return 0
    checksum = ord(data[-2:-1]) * 256 + ord (data[-1:])
    runningCount=0
    for i in range(len(data) - 2):
        runningCount += ord(data[i])
        runningCount %= 65536
    return (runningCount == checksum)

def verifySHAChecksum(data):
    if len(data) < 20:
        return 0
    m = sha.new()
    m.update(data[:-20])
    return m.digest() == data[-20:]

def decryptPrivateKey(keyRing, limit, numMPIs, passPhrase):
    hashes = ('Unknown', md5, sha, 'RIPE-MD/160', 'Double Width SHA',
              'MD2', 'Tiger/192', 'HAVAL-5-160')
    ciphers = ('Unknown', 'IDEA', DES3, CAST, Blowfish, 'SAFER-SK128',
               'DES/SK', AES, AES, AES)
    keySizes = (0, 0, 192, 128, 128, 0, 0, 128, 192, 256)
    legalCiphers = (2, 3, 4, 7, 8, 9)

    encryptType = getBlockType(keyRing)

    if encryptType == ENCRYPTION_TYPE_UNENCRYPTED:
        mpiList = []
        for i in range(0,numMPIs):
            mpiList.append(readMPI(keyRing))
        return mpiList

    if encryptType in (ENCRYPTION_TYPE_SHA1_CHECK,
                       ENCRYPTION_TYPE_S2K_SPECIFIED):
        algType=getBlockType(keyRing)
        if algType not in legalCiphers:
            if algType > len(ciphers) - 1:
                algType = 0
            raise IncompatibleKey('Cipher: %s unusable' %ciphers[algType])
        cipherAlg = ciphers[algType]
        s2kType = getBlockType(keyRing)
        hashType = getBlockType(keyRing)
        if hashType in (1, 2):
            hashAlg = hashes[hashType]
        else:
            if hashType > len(hashes) - 1:
                hashType = 0
            raise IncompatibileKey('Hash algortihm %s is not implemented. '
                                   'Key not readable' %hashes[hashType])
        # RFC 2440 3.6.1.1
        keySize = keySizes[algType]
        if not s2kType:
            key = simpleS2K(passPhrase, hashAlg, keySize)
        elif s2kType == 1:
            salt = keyRing.read(8)
            key = saltedS2K(passPhrase, hashAlg, keySize, salt)
        elif s2kType == 3:
            salt = keyRing.read(8)
            count = ord(keyRing.read(1))
            key = iteratedS2K(passPhrase,hashAlg, keySize, salt, count)
        data = keyRing.read(limit - keyRing.tell() + 1)
        if algType > 6:
            cipherBlockSize = 16
        else:
            cipherBlockSize = 8
        cipher = cipherAlg.new(key,1)
        FR = data[:cipherBlockSize]
        data = data[cipherBlockSize:]
        FRE = cipher.encrypt(FR)
        unenc = xorStr(FRE, data[:cipherBlockSize])
        i = 0
        while i + cipherBlockSize < len(data):
            FR=data[i:i + cipherBlockSize]
            i += cipherBlockSize
            FRE = cipher.encrypt(FR)
            unenc += xorStr(FRE, data[i:i + cipherBlockSize])
        if encryptType == ENCRYPTION_TYPE_S2K_SPECIFIED:
            check = verifyRFC2440Checksum(unenc)
        else:
            check = verifySHAChecksum(unenc)
        if not check:
            raise BadPassPhrase('Pass phrase incorrect')
        data = unenc
        index = 0
        r = []
        for count in range(numMPIs):
            MPIlen = (ord(data[index]) * 256 + ord(data[index+1]) + 7 ) / 8
            index += 2
            MPI = 0L
            for i in range(MPIlen):
                MPI = MPI * 256 + ord(data[index])
                index += 1
            r.append(MPI)
        return r
    raise MalformedKeyRing("Can't decrypt key. unkown string-to-key "
                           "specifier: %i" %encryptType)

def xorStr(str1, str2):
    r=''
    for i in range(0, min(len(str1), len(str2))):
        r += chr(ord(str1[i]) ^ ord(str2[i]))
    return r
