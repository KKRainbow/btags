from .terminalcontroller import TerminalController
from threading import Lock, current_thread
import os
#######################################################################
# Example use case: progress bar
#######################################################################

class ProgressBar:
    """
    A 3-line progress bar, which looks like::

                                Header
        20% [===========----------------------------------]
                           progress message

    The progress bar is colored, if the terminal supports color
    output; and adjusts to the width of the terminal.
    """
    BAR = '%3d%% ${GREEN}[${BOLD}%s%s${NORMAL}${GREEN}]${NORMAL}\n'
    HEADER = '${BOLD}${CYAN}%s${NORMAL}\n\n'

    def __init__(self, term, header, out):
        self.term = term
        if not (self.term.CLEAR_EOL and self.term.UP and self.term.BOL):
            raise ValueError("Terminal isn't capable enough -- you "
                             "should use a simpler progress dispaly.")
        self.width = self.term.COLS or 75
        self.bar = term.render(self.BAR).decode()
        self.header = self.term.render(self.HEADER % header.center(self.width))
        self.out = os.fdopen(out.fileno(), 'wb')
        self.cleared = 1  #: true if we haven't drawn the bar yet.
        self._last_message = None
        self.update(0, '')

    def update(self, percent, message):
        if self.cleared:
            self.out.write(self.header)
            self.cleared = 0
        if message is None:
            message = self._last_message
        else:
            self._last_message = message
        n = int((self.width - 10) * percent)
        bar = self.bar % (100 * percent, '=' * n, '-' * (self.width - 10 - n))
        self.out.write(
            self.term.BOL + self.term.UP + self.term.CLEAR_EOL +
            bar.encode() +
            self.term.CLEAR_EOL + message.center(self.width).encode()
        )
        self.out.flush()

    def clear(self):
        if not self.cleared:
            self.out.write(self.term.BOL + self.term.CLEAR_EOL +
                           self.term.UP + self.term.CLEAR_EOL +
                           self.term.UP + self.term.CLEAR_EOL)
            self.cleared = 1


class MultiProgressBar:
    def __init__(self, bar_count, bar_name_prefix, out):
        os.system("stty -echo -icanon")
        os.system("tput civis")
        self._term = TerminalController()
        self._bar_count = bar_count
        self._out = out
        self._out_lock = Lock()
        self.index_lock = Lock()
        self.last_allocated_index = -1
        self.allocated_index = set()
        self._bar = list()
        self._bar_end_lines = list()
        for i in range(1, bar_count + 1):
            self._bar.append(ProgressBar(self._term, "{}{}".format(bar_name_prefix, i), out))
            self._out.flush()
            self._bar_end_lines.append(self._term.LINES - 3 * (bar_count - i))

    def _set_pos_to_bar(self, index):
        self._out.write(self._term.set_pos(self._bar_end_lines[index], 1))

    def update(self, index, percent, message):
        assert percent <= 1
        with self._out_lock:
            self._set_pos_to_bar(index)
            self._out.flush()
            self._bar[index].update(percent, message)

    def get_an_index(self):
        with self.index_lock:
            for i in range(self._bar_count):
                self.last_allocated_index += 1
                self.last_allocated_index %= self._bar_count
                if self.last_allocated_index not in self.allocated_index:
                    self.allocated_index.add(self.last_allocated_index)
                    return self.last_allocated_index
        assert False
        return -1

    def return_an_index(self, index):
        with self.index_lock:
            assert index in self.allocated_index
            self.allocated_index.remove(index)

    def __del__(self):
        os.system("stty echo icanon")
        os.system("tput cnorm")
