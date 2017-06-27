from concurrent.futures.thread import ThreadPoolExecutor as PoolExecutor
from concurrent.futures import as_completed
from btagslib.terminal.statusbar import MultiProgressBar, get_status_bar_decorator


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
    def __init__(self, task_generator, concurrency_level, status_bar: MultiProgressBar):
        self.task_generator = task_generator
        self._concurrency_level = concurrency_level
        self._status_bar = status_bar
        self._status_bar_index = status_bar.get_an_index()
        self._status_bar_decorator = get_status_bar_decorator(status_bar, self._status_bar_index)
        self.task_submitted = list()

    def submit_task(self, executor: PoolExecutor):
        i = 0
        for task in self.task_generator.iter_tasks():
            i += 1
            self.task_submitted.append(executor.submit(task.start))

    def run(self):
        with PoolExecutor(max_workers=self._concurrency_level) as executor:
            add_task_future = executor.submit(self.submit_task, executor)
            try:
                add_task_future.result()
            except Exception as e:
                raise RunnerError("Error when add task: {}".format(e))

            @self._status_bar_decorator(0, 1, len(self.task_submitted), "Task finished {0}/{1}", True)
            def get_result(future):
                future.result()
            for future in as_completed(self.task_submitted):
                get_result(future)
