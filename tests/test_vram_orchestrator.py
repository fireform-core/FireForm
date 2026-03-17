import asyncio
import pytest
from src.core.orchestrator import orchestrator

@pytest.mark.asyncio
async def test_orchestrator_lock_serialization():
    """
    Verify that the VRAMOrchestrator lock correctly serializes concurrent requests.
    """
    execution_order = []

    async def task(name, duration):
        async with orchestrator.lock:
            execution_order.append(f"{name}_start")
            await asyncio.sleep(duration)
            execution_order.append(f"{name}_end")

    # Launch two tasks concurrently
    # Task 1 starts first but takes longer
    # Task 2 should wait for Task 1 to finish
    await asyncio.gather(
        task("A", 0.5),
        task("B", 0.1)
    )

    # If locking works, Task B must start AFTER Task A ends
    assert execution_order == ["A_start", "A_end", "B_start", "B_end"]

@pytest.mark.asyncio
async def test_orchestrator_singleton():
    """
    Verify that VRAMOrchestrator follows the singleton pattern.
    """
    from src.core.orchestrator import VRAMOrchestrator
    o1 = VRAMOrchestrator()
    o2 = VRAMOrchestrator()
    assert o1 is o2
    assert o1.lock is o2.lock
