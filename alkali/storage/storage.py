class Storage:
    """
    helper base class for the Storage object hierarchy
    """

    def __init__(self, *args, **kw ):
        pass

    @property
    def _name(self):
        return self.__class__.__name__
