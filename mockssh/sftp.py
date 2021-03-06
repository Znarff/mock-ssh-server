import logging
import operator
import os

from errno import EACCES, EDQUOT, EPERM, EROFS, ENOENT, ENOTDIR

import paramiko


__all__ = [
    "SFTPServer",
]


class SFTPHandle(paramiko.SFTPHandle):

    log = logging.getLogger(__name__)

    def __init__(self, file_obj, flags=0):
        super(SFTPHandle, self).__init__(flags)
        self.file_obj = file_obj

    @property
    def readfile(self):
        return self.file_obj

    @property
    def writefile(self):
        return self.file_obj


LOG = logging.getLogger(__name__)


def returns_sftp_error(func):

    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except OSError as err:
            LOG.debug("Error calling %s(%s, %s): %s",
                      func, args, kwargs, err, exc_info=True)
            errno = err.errno
            if errno in {EACCES, EDQUOT, EPERM, EROFS}:
                return paramiko.SFTP_PERMISSION_DENIED
            if errno in {ENOENT, ENOTDIR}:
                return paramiko.SFTP_NO_SUCH_FILE
            return paramiko.SFTP_FAILURE
        except Exception as err:
            LOG.debug("Error calling %s(%s, %s): %s",
                      func, args, kwargs, err, exc_info=True)
            return paramiko.SFTP_FAILURE

    return wrapped


class SFTPServerInterface(paramiko.SFTPServerInterface):

    log = logging.getLogger(__name__)

    def __init__(self, server, *largs, **kwargs):
        super(SFTPServerInterface, self).__init__(server, *largs, **kwargs)

    def session_started(self):
        pass

    def session_ended(self):
        pass

    @returns_sftp_error
    def open(self, path, flags, attr):
        fd = os.open(path, flags)
        self.log.debug("open(%s): fd: %d", path, fd)
        if flags & (os.O_WRONLY | os.O_RDWR):
            mode = "w"
        elif flags & (os.O_APPEND):
            mode = "a"
        else:
            mode = "r"
        mode += "b"
        self.log.debug("open(%s): Mode: %s", path, mode)
        return SFTPHandle(os.fdopen(fd, mode), flags)

    @returns_sftp_error
    def stat(self, path):
        st = os.stat(path)
        return paramiko.SFTPAttributes.from_stat(st, path)

    @returns_sftp_error
    def mkdir(self, path, attr):
        os.mkdir(path, attr.st_mode)
        return paramiko.SFTP_OK

    @returns_sftp_error
    def list_folder(self, path):
        abspath = os.path.abspath(path)
        content = [paramiko.SFTPAttributes.from_stat(entry.stat(), entry.path)
                   for entry in os.scandir(abspath)]
        return sorted(content, key=operator.attrgetter('filename'))

    @returns_sftp_error
    def remove(self, path):
        os.remove(path)
        return paramiko.SFTP_OK

    @returns_sftp_error
    def rmdir(self, path):
        os.rmdir(path)
        return paramiko.SFTP_OK


class SFTPServer(paramiko.SFTPServer):

    def __init__(self, channel, name, server, sftp_si=SFTPServerInterface,
                 *largs, **kwargs):
        kwargs["sftp_si"] = SFTPServerInterface
        super(SFTPServer, self).__init__(channel, name, server, *largs,
                                         **kwargs)
