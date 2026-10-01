import asyncio

from app.jobs import JobRunner


async def test_rejects_duplicate_while_running():
    j = JobRunner()
    gate = asyncio.Event()

    async def job():
        await gate.wait()

    assert j.submit("k", job) is True
    assert j.submit("k", job) is False
    gate.set()
    await j.wait_all()
    assert j.submit("k", job) is True
    await j.wait_all()


async def test_exception_frees_key():
    j = JobRunner()

    async def boom():
        raise RuntimeError("x")

    j.submit("k", boom)
    await j.wait_all()
    assert not j.is_running("k")


async def test_submit_coalesced_reruns_once_after_running_job():
    runs = 0
    gate = asyncio.Event()

    async def job():
        nonlocal runs
        runs += 1
        if runs == 1:
            await gate.wait()

    j = JobRunner()
    j.submit_coalesced("k", job)
    await asyncio.sleep(0)
    j.submit_coalesced("k", job)
    j.submit_coalesced("k", job)
    gate.set()
    await j.wait_all()
    assert runs == 2


async def test_cancel_stops_job_and_frees_key():
    j = JobRunner()
    stopped = asyncio.Event()

    async def job():
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    j.submit("p:a", job)
    j.submit("p:b", job)
    j.submit("q:a", job)
    await asyncio.sleep(0)
    assert sorted(j.keys("p:")) == ["p:a", "p:b"]
    await j.cancel(j.keys("p:"))
    assert stopped.is_set() and j.keys("p:") == [] and j.is_running("q:a")
    await j.cancel(["q:a", "missing"])
    assert not j.is_running("q:a")
