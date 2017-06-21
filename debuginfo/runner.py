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


class Runner:
    def __init__(self, task_generator):
        self.task_generator = task_generator

    def run(self):
        for task in self.task_generator:
            task.start()
