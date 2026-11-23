import pytest

from app import worker as worker_mod


@pytest.fixture(autouse=True)
def drain_background_jobs(monkeypatch):
    """Wait for every background job a test started, so jobs never overlap with the next test."""
    created = []
    original = worker_mod.Worker.__init__

    def tracking(self, *args, **kwargs):
        original(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(worker_mod.Worker, "__init__", tracking)
    yield
    for w in created:
        w.pool.shutdown(wait=True)
