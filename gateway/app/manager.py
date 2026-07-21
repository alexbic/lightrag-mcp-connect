from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class WorkspaceProcess:
    slug: str
    port: int
    process: asyncio.subprocess.Process
    last_used: float
    active_requests: int = 0


class WorkspaceProcessManager:
    """Lazily runs one official lightrag-server process per active workspace."""

    def __init__(
        self,
        *,
        first_port: int = 9700,
        max_instances: int = 16,
        working_root: str = "/app/data/rag_storage",
        input_root: str = "/app/data/inputs",
        startup_timeout: float = 90.0,
    ):
        self.first_port = first_port
        self.max_instances = max_instances
        self.working_root = Path(working_root)
        self.input_root = Path(input_root)
        self.startup_timeout = startup_timeout
        self.instances: dict[str, WorkspaceProcess] = {}
        self.pool_lock = asyncio.Lock()
        self.client = httpx.AsyncClient(timeout=None)

    async def close(self) -> None:
        await self.client.aclose()
        await asyncio.gather(
            *(self._stop(instance) for instance in list(self.instances.values())),
            return_exceptions=True,
        )

    @staticmethod
    def storage_workspace_for(slug: str) -> str:
        return os.getenv("WORKSPACE_MAIN_STORAGE_NAME", "") if slug == "main" else slug

    async def acquire(self, slug: str) -> WorkspaceProcess:
        current = self.instances.get(slug)
        if current and current.process.returncode is None:
            current.last_used = time.monotonic()
            current.active_requests += 1
            return current
        async with self.pool_lock:
            current = self.instances.get(slug)
            if current and current.process.returncode is None:
                current.last_used = time.monotonic()
                current.active_requests += 1
                return current
            if len(self.instances) >= self.max_instances:
                idle = [
                    item
                    for item in self.instances.values()
                    if item.active_requests == 0
                ]
                if not idle:
                    raise RuntimeError("all cached workspace processes are busy")
                victim = min(idle, key=lambda item: item.last_used)
                await self._stop(victim)
                self.instances.pop(victim.slug, None)
            port = self._free_port()
            instance = await self._start(slug, port)
            instance.active_requests = 1
            self.instances[slug] = instance
            return instance

    @staticmethod
    def release(instance: WorkspaceProcess) -> None:
        instance.active_requests = max(0, instance.active_requests - 1)
        instance.last_used = time.monotonic()

    def _free_port(self) -> int:
        used = {item.port for item in self.instances.values()}
        for port in range(self.first_port, self.first_port + self.max_instances):
            if port not in used:
                return port
        raise RuntimeError("workspace process port pool is exhausted")

    async def _start(self, slug: str, port: int) -> WorkspaceProcess:
        # Empty workspace preserves LightRAG's legacy PostgreSQL `default`
        # workspace and the existing root-level NetworkX files.
        storage_workspace = self.storage_workspace_for(slug)
        self.working_root.mkdir(parents=True, exist_ok=True)
        input_dir = self.input_root if slug == "main" else self.input_root / slug
        input_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["HOST"] = "127.0.0.1"
        env["PORT"] = str(port)
        env["WORKSPACE"] = storage_workspace
        env["WORKING_DIR"] = str(self.working_root)
        env["INPUT_DIR"] = str(input_dir)
        env["LIGHTRAG_API_KEY"] = os.environ["LIGHTRAG_SERVER_KEY"]
        process = await asyncio.create_subprocess_exec(
            "lightrag-server",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workspace",
            storage_workspace,
            "--working-dir",
            str(self.working_root),
            "--input-dir",
            str(input_dir),
            env=env,
        )
        deadline = time.monotonic() + self.startup_timeout
        headers = {"X-API-Key": env["LIGHTRAG_API_KEY"]}
        while time.monotonic() < deadline:
            if process.returncode is not None:
                raise RuntimeError(
                    f"lightrag-server for {slug!r} exited with {process.returncode}"
                )
            try:
                response = await self.client.get(
                    f"http://127.0.0.1:{port}/health", headers=headers, timeout=2
                )
                if response.status_code == 200:
                    return WorkspaceProcess(slug, port, process, time.monotonic())
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
        process.terminate()
        await process.wait()
        raise TimeoutError(f"workspace {slug!r} did not start in time")

    async def _stop(self, instance: WorkspaceProcess) -> None:
        if instance.process.returncode is not None:
            return
        instance.process.terminate()
        try:
            await asyncio.wait_for(instance.process.wait(), timeout=10)
        except TimeoutError:
            instance.process.kill()
            await instance.process.wait()
