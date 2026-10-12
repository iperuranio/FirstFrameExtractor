"""--quit, for the Nexus app: the copy started with it asks the open copy to close, and ends at once.

The open copy listens on a local socket named after the app, for this user only (QLocalServer: a named
pipe on Windows, a Unix socket on macOS). A copy started with --quit connects, writes QUIT and reads the
answer: the open copy closes as its window would (OK), unless an extraction is running, in which case it
stays open and answers BUSY: Nexus then leaves the update for later (its release contract, section 1).

Exit codes of a --quit copy: 0 asked and closing, 1 none open, 3 busy, 4 open but no answer.
"""

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "dev.metessi.first-frame-extractor"
QUIT = b"QUIT\n"
OK = b"OK\n"
BUSY = b"BUSY\n"

EXIT_CLOSING = 0
EXIT_NONE_OPEN = 1
EXIT_BUSY = 3
EXIT_NO_ANSWER = 4

TIMEOUT_MS = 3000


def request_quit(name: str = SERVER_NAME) -> int:
    """Asks the open copy to close; the exit code of the --quit copy."""
    if QCoreApplication.instance() is None:
        QCoreApplication([])
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(TIMEOUT_MS):
        return EXIT_NONE_OPEN
    socket.write(QUIT)
    socket.flush()
    answer = b""
    while not answer.endswith(b"\n") and socket.waitForReadyRead(TIMEOUT_MS):
        answer += bytes(socket.readAll())
    socket.disconnectFromServer()
    return {OK: EXIT_CLOSING, BUSY: EXIT_BUSY}.get(answer, EXIT_NO_ANSWER)


class QuitListener:
    """In the open copy: answers a --quit copy. `busy()` says whether closing now would lose work,
    `close()` closes the app as its window would."""

    def __init__(self, busy, close, name: str = SERVER_NAME):
        self._busy = busy
        self._close = close
        self.server = QLocalServer()
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)
        self.listening = self._listen(name)

    def _listen(self, name: str) -> bool:
        # Another open copy answers already: it is the one a --quit closes. Asked before listening,
        # because with UserAccessOption Qt binds elsewhere and renames over the name: a second listen
        # would take the name away from the first copy.
        probe = QLocalSocket()
        probe.connectToServer(name)
        if probe.waitForConnected(500):
            probe.disconnectFromServer()
            return False
        # What a copy that crashed left behind (a Unix socket): nobody answers there.
        QLocalServer.removeServer(name)
        return self.server.listen(name)

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            # What arrived before the signal was connected does not signal again.
            self._read(socket)

    def _read(self, socket):
        if not bytes(socket.peek(64)).endswith(b"\n"):
            return
        line = bytes(socket.readAll())
        if line != QUIT:
            socket.disconnectFromServer()
            return
        if self._busy():
            socket.write(BUSY)
            socket.flush()
            return
        socket.write(OK)
        socket.flush()
        socket.waitForBytesWritten(TIMEOUT_MS)
        self._close()
