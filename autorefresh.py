#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# MIT License
#
# Copyright (c) 2023 Stanley Zhang
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Serve a file. Trigger browser refresh on SIGHUP.

This script is intended for usage with `latexmk -pvc`, e.g.:
```
$pdf_previewer = "./autorefresh.py";
$pdf_update_method = 2;     # via signal
$pdf_update_signal = 1;     # SIGHUP
```

"""

import argparse
from http import (
    HTTPStatus,
)
from http.server import (
    ThreadingHTTPServer,
    BaseHTTPRequestHandler,
)
import mimetypes
import logging
import shutil
import signal
import sys
import threading

log = logging.getLogger(__name__)

indexData = rb'''<!doctype html>
<html>
<script>
    window.onload = function onload() {
        const fileFrame = document.getElementById('fileFrame');
        const errorElem = document.getElementById('error');
        const fileSrc = fileFrame.src;

        function setError(msg) {
            if (!msg) {
                errorElem.classList.add('hidden');
                errorElem.textContent = '';
                return;
            }

            errorElem.classList.remove('hidden');
            errorElem.textContent = msg;
        }

        function createEventSource() {
            eventSource = new EventSource('/refresh');
            eventSource.addEventListener('open', function onopen(event) {
                console.log(event);
                setError(null);
            });
            eventSource.addEventListener('refresh', function onrefresh(event) {
                console.log(event);
                setError(null);
                fileFrame.src = fileSrc;
            });
            eventSource.addEventListener('error', function onerror(event) {
                console.log(event);
                setError('connection lost: ' + Date());
                event.target.close();

                // try to re-establish connection
                setTimeout(createEventSource, 5000);
            });
        }

        createEventSource();
    };
</script>
<style>
    body {
        margin: 0;
        display: flex;
        flex-flow: column nowrap;
        height: 100vh;
    }
    #error {
        margin: 0;
        background: red;
        color: white;
    }
    #error.hidden {
        display: none;
    }
    iframe#fileFrame {
        border: 0;
        flex: 1;
    }
</style>
    <head>
        <title>File</title>
    </head>
    <body>
        <pre id="error" class="hidden"></pre>
        <iframe
            id="fileFrame"
            src="/file"
        >
        </iframe>
    </body>
</html>
'''

refreshLock = threading.Lock()
refreshCond = threading.Condition(refreshLock)
refreshId = 0

REFRESH_ID_MAX = 2 ** 16

def handleSighup(signum, frame):
    global refreshId

    with refreshCond:
        refreshId = (refreshId + 1) % REFRESH_ID_MAX
        refreshCond.notify_all()

class FileHandler(BaseHTTPRequestHandler):
    FILE_PATH = None        # File to serve.
    FILE_MIMETYPE = None    # File's MIME type.

    def log_message(self, format, *args, **kwargs):
        log.info(format, *args, **kwargs)

    def handleRefresh(self):
        self.protocol_version = 'HTTP/1.1'
        self.send_response(HTTPStatus.OK)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()

        self.wfile.write(b'data:\n\n')  # initial message
        self.wfile.flush()

        while True:
            with refreshCond:
                lastMsgId = refreshId
                while refreshId <= lastMsgId:
                    isTimeout = not refreshCond.wait(timeout=60)
                    if isTimeout:
                        break

            if isTimeout:
                msg = ': {}\n\n'.format(lastMsgId)  # keepalive
            else:
                msg = 'event: refresh\ndata: {}\n\n'.format(lastMsgId)
                log.info('%r', msg)

            self.wfile.write(msg.encode())
            self.wfile.flush()

    def do_GET(self):
        try:
            if self.path == '/refresh':
                return self.handleRefresh()

            if self.path == '/':
                self.protocol_version = 'HTTP/1.1'
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(indexData)
                return

            if self.path == '/file':
                self.protocol_version = 'HTTP/1.1'
                self.send_response(HTTPStatus.OK)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Type', self.FILE_MIMETYPE)
                self.end_headers()
                with open(self.FILE_PATH, 'rb') as file:
                    shutil.copyfileobj(file, self.wfile)
                    return

            self.send_error(HTTPStatus.NOT_FOUND)
        except BrokenPipeError as e:
            return  # Connection closed, nothing to do.

def main(argv):
    parser = argparse.ArgumentParser(
        description='Serve a file. Trigger browser refresh on SIGHUP.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        'filePath',
        help='Path to file to serve.',
    )
    parser.add_argument(
        '--mime',
        help='File MIME type; auto-detected if unset.'
    )
    parser.add_argument(
        '--port', type=int, default=8080,
        help='Port number to serve on.'
    )
    args = parser.parse_args(argv)

    if not args.mime:
        args.mime, _ = mimetypes.guess_type(args.filePath)
        log.info(
            'MIME type: guessed %r from filePath: %r',
            args.mime, args.filePath,
        )

    FileHandler.FILE_PATH = args.filePath
    FileHandler.FILE_MIMETYPE = args.mime

    signal.signal(signal.SIGHUP, handleSighup)

    server = ThreadingHTTPServer(('', args.port), FileHandler)
    log.info('Serving on port %d', args.port)
    server.serve_forever()

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            '%(name)s[%(process)d] '
            '%(filename)s:%(lineno)d: %(message)s'
        ),
    )
    sys.exit(main(sys.argv[1:]))

