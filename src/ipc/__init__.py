#!/usr/bin/env python2

import pickle

class EmptyMessage(object):
    '''
    An empty message passed from source to target within the ProcessList.
    This is the base class for all messages.
    '''
    def __init__(self, target):
        self.target=target

    def __str__(self):
        return "{0} to {1}".format(type(self).__name__, self.target)

class StringMessage(EmptyMessage):
    '''
    A message containing a string argument
    '''
    def __init__(self, target, message):
        self.message=message
        super(StringMessage, self).__init__(target)

    def __str__(self):
        return '{0};"{1}"'.format(super(StringMessage,self).__str__(), self.message)

class PrntMessage(StringMessage):
    '''
    Class for use by client.Process.prnt.  Don't send this unless you know
    what you're doing
    '''

    def __str__(self):
        return str(self.message)

class FileMessage(EmptyMessage):
    '''
    Base class for all messages informing recipients about a file being
    generated
    '''
    def __init__(self, target, filename):
        self.filename=filename
        super(FileMessage, self).__init__(target)

    def __str__(self):
        return "{0}:{1}".format(super(FileMessage, self).__str__(), self.filename)

class QueryMessage(EmptyMessage):
    '''
    Base class for queries like id queries and inpt queries.  Don't send
    this unless you know what you're doing.
    '''
    def __init__(self, target, source):
        self.source=source
        super(QueryMessage, self).__init__(target)

    def __str__(self):
        return "{0} from {1} to {2}".format(
          type(self).__name__, self.source, self.target
        )

class InputMessage(QueryMessage):
    '''
    A message signifying we want user input, used by client.Process.Inpt.
    '''
    def __init__(self, target, source, prompt=None):
        self.prompt=prompt
        super(InputMessage, self).__init__(target, source)

    def __str__(self):
        return "{0}: {1}".format(
          super(InputMessage, self).__str__(), self.prompt
        )

class InputResponseMessage(StringMessage):
    '''
    A response to an InputMessage.  Don't send this unless you know what
    you're doing.
    '''
    pass

class GetIdsMessage(QueryMessage):
    '''
    A message requesting the ids of concurrent processess, used by
    client.Process.get_ids.
    '''
    def __init__(self, target, source, name):
        self.name=name
        super(GetIdsMessage, self).__init__(target, source)

    def __str__(self):
        return "{0} about {1}".format(
          super(GetIdsMessage, self).__str__(), self.name
        )

class IdsReplyMessage(EmptyMessage):
    '''
    A message replying to an id query with the ids requested.  Don't send
    this unless you know what you're doing.
    '''
    def __init__(self, target, ids):
        self.ids=ids
        super(IdsReplyMessage, self).__init__(target)

    def __str__(self):
        return "{0}: {1}".format(
          super(IdsReplyMessage, self).__str__(), self.ids
        )

class ExceptionMessage(EmptyMessage):
    '''
    A system message passed when an exception is trapped
    '''
    def __init__(self, target, source, e):
        self.source=source
        self.pickled_e=pickle.dumps(e,pickle.HIGHEST_PROTOCOL)
        super(ExceptionMessage, self).__init__(target)

    def rais(self):
        raise pickle.loads(self.pickled_e) # Passing on exception from sub process

    def __repr__(self):
        return "From {0}:{1}".format(self.source, str(super(ExceptionMessage, self)))

    def __str__(self):
        return str(pickle.loads(self.pickled_e))

class ResidentTermMessage(EmptyMessage):
    pass

### Test code ############################################################

import unittest, time

class Test_Messages(unittest.TestCase):
    def test_EmptyMessage(self):
        m = EmptyMessage("target")
        self.assertEqual(str(m),'EmptyMessage to target')

    def test_StringMessage(self):
        m = StringMessage("target", "testmessage")
        self.assertEqual(str(m),'StringMessage to target;"testmessage"')

    def test_PrntMessage(self):
        m = PrntMessage("target", "testmessage")
        self.assertEqual(str(m),'testmessage')

    def test_FileMessage(self):
        m = FileMessage("target","filename")
        self.assertEqual(m.filename, "filename")
        self.assertEqual(str(m),'FileMessage to target:filename')

    def test_QueryMessage(self):
        m = QueryMessage("target", "source")
        self.assertEqual(m.source, "source")
        self.assertEqual(str(m),'QueryMessage from source to target')

    def test_InputMessage(self):
        m = InputMessage("target","source", "prompt")
        self.assertEqual(m.source, "source")
        self.assertEqual(m.prompt,"prompt")
        self.assertEqual(str(m),'InputMessage from source to target: prompt')

    def test_GetIdsMessage(self):
        m = GetIdsMessage("target", "source", "name")
        self.assertEqual(m.source, "source")
        self.assertEqual(m.name,"name")
        self.assertEqual(str(m),'GetIdsMessage from source to target about name')
    def test_IdsReplyMessage(self):
        m = IdsReplyMessage("target", "response")
        self.assertEqual(m.ids,"response")
        self.assertEqual(str(m),'IdsReplyMessage to target: response')

    def test_ExceptionMessage(self):
        e = Exception("testmessage")
        m = ExceptionMessage("target", "source", e)
        self.assertEqual(m.source, "source")
        self.assertEqual(str(m), "testmessage")

    def test_ResidentTermMessage(self):
        m = ResidentTermMessage("target")
        self.assertEqual(str(m),'ResidentTermMessage to target')

if __name__=='__main__':
    unittest.main()
