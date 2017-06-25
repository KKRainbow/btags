from concurrent.futures.thread import ThreadPoolExecutor as PoolExecutor
from concurrent.futures import as_completed
import signal


class Task:
    def _before_run(self):
        pass

    def _run(self):
        pass

    def _after_run(self):
        pass

    def start(self):
        self._before_run()
        self._run()
        self._after_run()


class RunnerError(Exception):
    pass


class Runner:
    def __init__(self, task_generator, concurrency_level):
        self.task_generator = task_generator
        self._concurrency_level = concurrency_level
        self.task_submitted = list()

    def submit_task(self, executor: PoolExecutor):
        i = 0
        for task in self.task_generator.iter_tasks():
            i += 1
            self.task_submitted.append(executor.submit(task.start))

    def run(self):
        with PoolExecutor(max_workers=self._concurrency_level) as executor:
            def interrupt_handler(signal, frame):
                import os
                os.system("tput cnorm")
                raise KeyboardInterrupt()
            signal.signal(signal.SIGINT, interrupt_handler)
            add_task_future = executor.submit(self.submit_task, executor)
            try:
                add_task_future.result()
            except Exception as e:
                raise RunnerError("Error when add task: {}".format(e))
            i = len(self.task_submitted)
            for future in as_completed(self.task_submitted):
                try:
                    future.result()
                except:
                    raise
                else:
                    pass
                finally:
                    i -= 1
