from itertools import ifilterfalse
import logging
import re
from restkit import Resource, Response
import errors

USER_AGENT = 'pyRTkit/{0}'.format('0.0.1')

class RTResource(Resource):
    def __init__(self, uri, **kwargs):
        kwargs['response_class'] = RTResponse
        super(RTResource, self).__init__(uri, **kwargs)
        self.logger = logging.getLogger('rtkit')

    def request(self, method, path=None, payload=None, headers=None, **kwargs):
        headers = headers or dict()
        headers.setdefault('Accept', 'text/plain')
        headers.setdefault('User-Agent', USER_AGENT)
        if payload and not hasattr(payload, 'read') \
            and not isinstance(payload, basestring):
            payload = self.encode(payload)
            headers.setdefault('Content-Type',
                               'application/x-www-form-urlencoded')
        self.logger.debug('{0} {1}'.format(method, path))
        self.logger.debug(headers)
        self.logger.debug('%r'%payload)
        return super(RTResource, self).request(
            method,
            path=path,
            payload=payload,
            headers=headers,
            **kwargs
        )

    @staticmethod
    def encode(payload):
        r'''Encode a dictionary into a valid RT query string
        >>> payload = {'spam': 1, 'ham':2, 'eggs':3, }
        >>> RTResource.encode(payload)
        u'content=eggs: 3\nham: 2\nspam: 1\n'
        '''
        pstr = ['{0}: {1}'.format(k,v) for k,v in payload.iteritems()]
        return u'content={0}\n'.format('\n'.join(pstr))


class RTResponse(Response):
    HEADER_PATTERN = '^RT/(?P<v>\d+\.\d+\.\d+)\s+(?P<s>(?P<i>\d+).+)$'
    HEADER = re.compile(HEADER_PATTERN)
    COMMENT_PATTERN = '^#\s+'
    COMMENT = re.compile(COMMENT_PATTERN)

    def __init__(self, connection, request, resp):
        self.logger = logging.getLogger('rtkit')
        self.logger.info('HTTP_STATUS: {0}'.format(resp.status))
        if resp.status_int == 200:
            resp_header = resp.body.next().strip()
            self.logger.debug(resp_header)
            r = self.HEADER.match(resp_header)
            if r:
                resp.version = tuple([int(v) for v in r.group('v').split('.')])
                resp.status = r.group('s')
                resp.status_int = int(r.group('i'))
            else:
                self.logger.error('"{0}" is not valid'.format(resp_header))
                resp.status = resp_header
                resp.status_int = 500
        super(RTResponse, self).__init__(connection, request, resp)
        self.logger.info('RESOURCE_STATUS: {0}'.format(self.status))

    @property
    def parsed(self):
        '''Return a list of 2-tuples lists representing resourses' attributes
        '''
        body = self.body_string()
        self.logger.debug('%r'%body)
        return self._parse(body)

    @classmethod
    def _parse(cls, body):
        '''Return a list of RFC5322-like section
        >>> body = """
        ...
        ... # c1
        ... spam: 1
        ... ham: 2,
        ...     3
        ... eggs:"""
        >>> RTResponse._parse(body)
        [[('spam', '1'), ('ham', '2, 3'), ('eggs', '')]]
        >>> RTResponse._parse('# spam 1 does not exist.')
        []
        '''
        section = cls._build(body)
        if len(section) == 1:
            try:
                errors.check(section[0])
            except errors.ResourceNotFound:
                section = ''
        return [cls._decode(lines) for lines in section]

    @classmethod
    def _decode(cls, lines):
        '''Return a list of 2-tuples parsing 'k: v' and skipping comments
        >>> l = [['# a b', 'spam: 1', 'ham: 2, 3'], ['# c', 'spam: 4', 'ham:']]
        >>> RTResponse._decode(['# c1 c2', 'spam: 1', 'ham: 2, 3', 'eggs:'])
        [('spam', '1'), ('ham', '2, 3'), ('eggs', '')]
        '''
        lines = ifilterfalse(cls.COMMENT.match, lines)
        return [(k, v.strip(' ')) for k,v in [l.split(':', 1) for l in lines]]

    @classmethod
    def _build(cls, body):
        '''Build logical lines from a RFC5322-like string
        >>> body = """
        ... # a
        ...   b
        ... spam: 1
        ... 
        ... ham: 2,
        ...     3
        ... --
        ... # c
        ... spam: 4
        ... ham:
        ... """
        >>> RTResponse._build(body)
        [['# a b', 'spam: 1', 'ham: 2, 3'], ['# c', 'spam: 4', 'ham:']]
        '''
        def build_section(section):
            logic_lines = []
            for line in filter(None, section.splitlines()):
                if line[0].isspace():
                   logic_lines[-1] += ' '+line.strip(' ')
                else:
                   logic_lines.append(line)
            return logic_lines
        return [build_section(b) for b in body.split('--')]