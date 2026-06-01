import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.core.config import settings
from backend.rag.indexer import RagIndexer


class MarkdownChangeHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        self.indexer = RagIndexer()

    def on_modified(self, event) -> None:  # noqa: ANN001
        if not event.is_directory and str(event.src_path).endswith(".md"):
            self.indexer.reindex_all()


def run() -> None:
    settings.vault_path.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    observer.schedule(MarkdownChangeHandler(), str(settings.vault_path), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    run()
