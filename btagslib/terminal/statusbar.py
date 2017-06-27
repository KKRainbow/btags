from .terminalcontroller import TerminalController
from threading import Lock
import os
import signal
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
        self._prev_handler = signal.getsignal(signal.SIGINT)

        def interrupt_handler(signal, frame):
            import os
            os.system("stty echo icanon")
            os.system("tput cnorm")
            raise KeyboardInterrupt()
        signal.signal(signal.SIGINT, interrupt_handler)
        self.term = TerminalController()
        self._bar_count = bar_count
        self._out = out
        self._out_lock = Lock()
        self.index_lock = Lock()
        self.last_allocated_index = -1
        self.allocated_index = set()
        self._bar = list()
        self._bar_end_lines = list()
        for i in range(1, bar_count + 1):
            self._bar.append(ProgressBar(self.term, "{}{}".format(bar_name_prefix, i), out))
            self._bar_end_lines.append(self.term.LINES - 4 * (bar_count - i) - 3)
            self._out.flush()
            self._out.write(self.term.DOWN.decode())
            self._out.write(self.term.DOWN.decode())
            self._out.flush()
        self._out.write(self.term.DOWN.decode())
        self._out.flush()

    def _set_pos_to_bar(self, index):
        self._out.write(self.term.set_pos(self._bar_end_lines[index], 1))

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

    def return_an_index(self, index):
        with self.index_lock:
            assert index in self.allocated_index
            self.allocated_index.remove(index)

    def __del__(self):
        os.system("stty echo icanon")
        os.system("tput cnorm")

    def info(self, index, str, color=None):
        if color is None:
            color = self.term.NORMAL
        with self._out_lock:
            self._out.write(
                self.term.set_pos(
                    self._bar_end_lines[index] + 1 if index is not None else self.term.LINES, 1
                )
            )
            self._out.flush()
            self._out.write(self.term.CLEAR_EOL.decode())
            self._out.flush()
            self._out.write(color.decode() + str)
            self._out.flush()


def get_status_bar_decorator(status_bar: MultiProgressBar, index: int):
    """
    use as following:
        >>> your_status_bar = MultiProgressBar()
        >>> your_decorator = get_status_bar_decorator(your_status_bar)
        >>> base, span, total_step, message = 0.5, 0.2, 1000, "Your Message {0} {1}"
        >>> @your_decorator(base, span, total_step, message)
        >>> def your_step_func(arg1, arg2, arg3):
        >>>     "Do something"
    this assume your step function will be called *total_step* times
    :param status_bar: MultiProgressBar
    :param index:int
    :return: int
    """
    def decorator_generator(base, span, total_step, message: str, force=False):
        cur_step = [0]

        def decorator(step_func):
            mydiv = pow(10, len(str(total_step)) - 3)
            if mydiv < 10:
                mydiv = 1

            def wrapper(*args):
                cur_step[0] += 1
                if force or cur_step[0] % mydiv == 0 or total_step - cur_step[0] <= mydiv:
                    status_bar.update(index, (cur_step[0] / total_step) * span + base,
                                      message.format(cur_step, total_step))
                step_func(*args)
            return wrapper
        return decorator
    return decorator_generator


