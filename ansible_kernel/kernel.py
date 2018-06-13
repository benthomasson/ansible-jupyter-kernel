from ipykernel.kernelbase import Kernel

from subprocess import check_output

import re
import yaml
from subprocess import Popen, STDOUT, PIPE
import logging
import traceback

from modules import modules

__version__ = '0.0.1'

logger = logging.getLogger('ansible_kernel.kernel')

version_pat = re.compile(r'version (\d+(\.\d+)+)')


class AnsibleKernel(Kernel):
    implementation = 'ansible_kernel'
    implementation_version = __version__

    @property
    def language_version(self):
        m = version_pat.search(self.banner)
        return m.group(1)

    _banner = None

    @property
    def banner(self):
        if self._banner is None:
            self._banner = check_output(['ansible', '--version']).decode('utf-8')
        return self._banner

    language_info = {'name': 'ansible',
                     'codemirror_mode': 'yaml',
                     'mimetype': 'text/yaml',
                     'file_extension': '.yml'}

    def __init__(self, **kwargs):
        Kernel.__init__(self, **kwargs)

    def process_output(self, output):
        if not self.silent:

            # Send standard output
            stream_content = {'name': 'stdout', 'text': output}
            self.send_response(self.iopub_socket, 'stream', stream_content)

    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        logger = logging.getLogger('ansible_kernel.kernel.do_execute')
        self.silent = silent
        if not code.strip():
            return {'status': 'ok', 'execution_count': self.execution_count,
                    'payload': [], 'user_expressions': {}}

        logger.debug('code %r', code)
        code_data = yaml.load(code)
        logger.debug('code_data %r', code_data)

        for module, args in code_data.items():
            if isinstance(args, dict):
                logger.debug('is dict')
                m_args = ' '.join(['{0}="{1}"'.format(k, v) for k, v in args.items()])
            elif isinstance(args, basestring):
                logger.debug('is string')
                m_args = args
            elif args is None:
                logger.debug('is None')
                m_args = ''
            else:
                logger.debug('is not supported %s', type(args))
                raise Exception("Not supported type {0}".format(type(args)))
            interrupted = False
            try:
                logger.debug("command %s", " ".join(['ansible', '-m', module, "-a", "{0}".format(m_args), '-i', 'localhost', 'localhost']))
                p = Popen(['ansible', '-m', module, "-a", "{0}".format(m_args), '-i', 'localhost', 'localhost'], stdout=PIPE, stderr=STDOUT)
                p.wait()
                exitcode = p.returncode
                logger.debug('exitcode %s', exitcode)
                output = p.communicate()[0]
                logger.debug('output %s', output)
                self.process_output(output)
            except KeyboardInterrupt:
                logger.error(traceback.format_exc())

        if interrupted:
            return {'status': 'abort', 'execution_count': self.execution_count}

        exitcode = 1

        if exitcode:
            error_content = {'execution_count': self.execution_count,
                             'ename': '', 'evalue': str(exitcode), 'traceback': []}

            self.send_response(self.iopub_socket, 'error', error_content)
            error_content['status'] = 'error'
            return error_content
        else:
            return {'status': 'ok', 'execution_count': self.execution_count,
                    'payload': [], 'user_expressions': {}}

    def do_complete(self, code, cursor_pos):
        code = code[:cursor_pos]
        default = {'matches': [], 'cursor_start': 0,
                   'cursor_end': cursor_pos, 'metadata': dict(),
                   'status': 'ok'}

        logger = logging.getLogger('ansible_kernel.kernel.do_complete')
        logger.debug('code %r', code)

        if not code or code[-1] == ' ':
            return default

        tokens = code.split()
        if not tokens:
            return default

        matches = []
        token = tokens[-1]
        start = cursor_pos - len(token)

        for module in modules:
            if module.startswith(token):
                matches.append(module)

        if not matches:
            return default
        matches = [m for m in matches if m.startswith(token)]

        return {'matches': sorted(matches), 'cursor_start': start,
                'cursor_end': cursor_pos, 'metadata': dict(),
                'status': 'ok'}

    def do_inspect(self, code, cursor_pos, detail_level=0):
        logger = logging.getLogger('ansible_kernel.kernel.do_inspect')
        logger.debug("code %s", code)
        logger.debug("cursor_pos %s", cursor_pos)
        logger.debug("detail_level %s", detail_level)

        data = dict()

        code_data = yaml.load(code)

        logger.debug("code_data %s", code_data)

        if isinstance(code_data, basestring):
            module = code_data
        elif isinstance(code_data, dict):
            module = code_data.keys()[0]
        else:
            logger.warn('code type not supported %s', type(code_data))
            return {'status': 'ok', 'data': {}, 'metadata': {}, 'found': False}

        logger.debug("command %s", " ".join(['ansible-doc', '-t', 'module', module]))
        p = Popen(['ansible-doc', '-t', 'module', module], stdout=PIPE, stderr=STDOUT)
        p.wait()
        exitcode = p.returncode
        logger.debug('exitcode %s', exitcode)
        output = p.communicate()[0]
        logger.debug('output %s', output)
        data['text/plain'] = output

        return {'status': 'ok', 'data': data, 'metadata': {}, 'found': True}
