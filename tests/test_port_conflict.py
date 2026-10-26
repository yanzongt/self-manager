import contextlib
import errno
import io
import os
import socket
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from serve import listening_pids, main


class PortConflictTests(unittest.TestCase):
    def test_start_script_reports_real_listener_pid(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.assertIn(os.getpid(), listening_pids(port))
            result = subprocess.run(
                [str(Path(__file__).resolve().parents[1] / 'start.sh'),
                 '--no-browser', '--port', str(port)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f'端口 {port} 已被占用', result.stderr)
            self.assertIn(f'占用进程 PID：{os.getpid()}', result.stderr)

    def test_ss_unavailable_falls_back_to_lsof(self):
        with patch('serve.shutil.which', side_effect=lambda name: name == 'lsof'), \
             patch('serve.subprocess.run', return_value=subprocess.CompletedProcess(
                 [], 0, '123\n456\n123\n', '')):
            self.assertEqual(listening_pids(8765), [123, 456])

    def test_lookup_failure_preserves_useful_startup_error(self):
        with patch('sys.argv', ['serve.py', '--port', '8877']), \
             patch('serve.load_investment', return_value=None), \
             patch('serve.create_server', side_effect=OSError(errno.EADDRINUSE, 'busy')), \
             patch('serve.listening_pids', return_value=[]), \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit):
                main()
            self.assertIn('端口 8877 已被占用', stderr.getvalue())
            self.assertIn('未能获取占用进程 PID', stderr.getvalue())

    def test_other_errors_do_not_query_port(self):
        with patch('sys.argv', ['serve.py']), \
             patch('serve.load_investment', return_value=None), \
             patch('serve.create_server', side_effect=PermissionError(errno.EACCES, 'denied')), \
             patch('serve.listening_pids') as lookup, \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit):
                main()
            lookup.assert_not_called()
            self.assertIn('denied', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
