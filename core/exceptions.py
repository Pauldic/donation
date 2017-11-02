

class SuspiousException(Exception):

    def __init__(self, message, errors=None):
        super(SuspiousException, self).__init__(message)
        self.errors = errors
