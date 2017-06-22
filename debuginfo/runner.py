from concurrent.futures.thread import ThreadPoolExecutor as PoolExecutor
from concurrent.futures import as_completed


class Task:
    def _before_run(self):
        print("A task begins!")

    def _run(self):
        pass

    def _after_run(self):
        print("A task ends!")

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
        for task in self.task_generator.iter_tasks():
            self.task_submitted.append(executor.submit(task.start))

    def run(self):
        with PoolExecutor(max_workers=self._concurrency_level) as executor:
            print("Waiting for submitting tasks...")
            add_task_future = executor.submit(self.submit_task, executor)
            try:
                add_task_future.result()
            except Exception as e:
                raise RunnerError("Error when add task: {}".format(e))
            print("All tasks is submitted")
            i = len(self.task_submitted)
            for future in as_completed(self.task_submitted):
                try:
                    future.result()
                except:
                    raise
                else:
                    print("{0} task remain...\r                          \r")
                finally:
                    i -= 1
