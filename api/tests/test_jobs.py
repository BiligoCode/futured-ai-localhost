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
