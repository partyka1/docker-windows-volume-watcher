"""
Exports ContainerNotifier enabling to notify containers about file changes in mounts.
"""

import logging
from os.path import relpath
import posixpath

import re
import docker

from docker_volume_watcher.debounce import debounce
from docker_volume_watcher.throttle import throttle
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


class NonZeroExitError(RuntimeError):
    """
    A non-zero exit code error from the command execution in docker.
    """

    def __init__(self, exit_code):
        super(NonZeroExitError, self).__init__()
        self.exit_code = exit_code


class ContainerNotifier(object):
    """
    Notifies container about file changes in binded host-directory.
    """

    def __init__(self, container, host_dir, container_dir):
        """
        Initialize a new instance of ContainerNotifier

        Args:
            container: Container
            host_dir (str): Host directory
            container_dir (str): Container directory
        """
        self.container = container
        self.host_dir = host_dir
        self.container_dir = container_dir

        event_handler = PatternMatchingEventHandler(ignore_directories=True)
        handler = self.__change_handler
        event_handler.on_created = handler
        event_handler.on_moved = handler
        event_handler.on_modified = handler

        self.ignore_file_pattern = '(\.idea|\.git|node_modules|___jb_old___|___jb_tmp___)'
        if self.ignore_file_pattern:
            self.ignore_file_pattern_compiled = re.compile(self.ignore_file_pattern)
        else:
            self.ignore_file_pattern_compiled = None
        self.observer = Observer()
        self.observer.schedule(event_handler, host_dir, recursive=True)
        self.observer.start()

    def __str__(self):
        return '%s -> %s:%s' % (self.host_dir, self.container.name, self.container_dir)

    def __change_handler(self, event):
        host_path = event.dest_path if hasattr(event, 'dest_path') else event.src_path
        relative_host_path = relpath(host_path, self.host_dir).replace('\\', '/')
        absolute_path = posixpath.join(self.container_dir, relative_host_path)

        if self.ignore_file_pattern_compiled and not self.is_ignored(relative_host_path):
            self.notify(absolute_path)

    def is_ignored(self, path):
        match = bool(re.search(self.ignore_file_pattern_compiled, path))
        return match

    # @throttle(mindelta=1, groupByArgIndex=1)
    @debounce(wait=1)
    def notify(self, absolute_path):
        """
        Notify container about change in file.

        Args:
            absolute_path (str): Absolute path of changed file.
        """

        logging.info(
            'Notifying container %s about change in %s',
            self.container.name,
            absolute_path)
        try:
            permissions = self.container.exec_run(
                ['stat', '-c', '%a', absolute_path], privileged=True)
            if permissions.exit_code != 0:
                raise NonZeroExitError(permissions.exit_code)
            permissions = permissions.output.decode('utf-8').strip()
            response = self.container.exec_run(
                ['chmod', permissions, absolute_path], privileged=True)
            if response.exit_code != 0:
                raise NonZeroExitError(response.exit_code)
            if response:
                logging.info(response.output.decode('utf-8').strip())
        except docker.errors.APIError:
            logging.error(
                'Failed to notify container %s about change in %s',
                self.container.name,
                absolute_path, exc_info=True)
        except NonZeroExitError as exception:
            logging.error(
                'Exec run returned non-zero exit code: %s',
                exception.exit_code)

    def stop(self):
        """
        Stop observing host directory.
        """

        self.observer.stop()
        self.observer.join()
