import json
import tempfile
import unittest
from pathlib import Path

from symphony_viewer import read_events


class SessionReaderTests(unittest.TestCase):
    def test_partial_append_and_private_reasoning(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            message = json.dumps({'type': 'response_item', 'payload': {'type': 'message', 'content': [{'text': '你好'}]}}).encode()
            private = json.dumps({'type': 'response_item', 'payload': {'type': 'reasoning', 'encrypted_content': 'secret'}}).encode()
            path.write_bytes(private + b'\n' + message[:30])
            first = read_events(path, 0)
            self.assertEqual(first['events'], [])
            self.assertEqual(first['offset'], len(private) + 1)
            with path.open('ab') as stream:
                stream.write(message[30:] + b'\n')
            second = read_events(path, first['offset'])
            self.assertEqual(len(second['events']), 1)
            self.assertEqual(second['events'][0]['data']['content'][0]['text'], '你好')
            self.assertEqual(read_events(path, second['offset'])['events'], [])


if __name__ == '__main__':
    unittest.main()
