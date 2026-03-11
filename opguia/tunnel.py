"""SSH tunnel manager — port-forward remote OPC UA endpoints.

Creates an SSH tunnel (ssh -L) to forward a local port to the remote
OPC UA server, so the client can connect via localhost.
"""

import asyncio
import random
from urllib.parse import urlparse

from loguru import logger

from opguia.utils import DEFAULT_OPC_PORT, EPHEMERAL_PORT_RANGE


def _find_free_port() -> int:
    """Pick a random high port that's likely free."""
    return random.randint(*EPHEMERAL_PORT_RANGE)


class SSHTunnel:
    """Manages a single SSH port-forwarding tunnel."""

    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self.local_port: int | None = None

    @property
    def active(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self, opc_url: str, ssh_host: str, ssh_user: str = "",
                    ssh_port: int = 22) -> str:
        """Start an SSH tunnel and return the local OPC UA URL.

        Args:
            opc_url:  Original OPC UA endpoint (e.g. opc.tcp://192.168.1.10:4840)
            ssh_host: SSH server hostname/IP to tunnel through
            ssh_user: SSH username (optional, uses system default if empty)
            ssh_port: SSH port (default 22)

        Returns:
            Local OPC UA URL pointing through the tunnel (e.g. opc.tcp://localhost:51234)
        """
        await self.stop()

        parsed = urlparse(opc_url)
        remote_host = parsed.hostname or "localhost"
        remote_port = parsed.port or DEFAULT_OPC_PORT

        self.local_port = _find_free_port()

        # Build ssh command
        target = f"{ssh_user}@{ssh_host}" if ssh_user else ssh_host
        cmd = [
            "ssh", "-N", "-L",
            f"{self.local_port}:{remote_host}:{remote_port}",
            target,
            "-p", str(ssh_port),
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=30",
            "-o", "ExitOnForwardFailure=yes",
        ]

        logger.debug("tunnel: {}", " ".join(cmd))

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait briefly for the tunnel to establish (or fail)
        try:
            await asyncio.wait_for(self._wait_for_tunnel(), timeout=10)
        except asyncio.TimeoutError:
            await self.stop()
            raise ConnectionError("SSH tunnel timed out — check SSH credentials and connectivity")

        if self._proc.returncode is not None:
            stderr = ""
            if self._proc.stderr:
                data = await self._proc.stderr.read()
                stderr = data.decode(errors="replace").strip()
            raise ConnectionError(f"SSH tunnel failed: {stderr or 'unknown error'}")

        return f"opc.tcp://localhost:{self.local_port}"

    async def _wait_for_tunnel(self):
        """Wait until the local port is accepting connections."""
        for _ in range(50):  # 50 * 0.2s = 10s max
            if self._proc.returncode is not None:
                return  # Process exited (error)
            try:
                _, writer = await asyncio.open_connection("localhost", self.local_port)
                writer.close()
                await writer.wait_closed()
                return  # Tunnel is up
            except (ConnectionRefusedError, OSError):
                await asyncio.sleep(0.2)

    async def stop(self):
        """Kill the SSH tunnel process."""
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None
        self.local_port = None

    @staticmethod
    async def ping(opc_url: str, ssh_host: str, ssh_user: str = "",
                   ssh_port: int = 22) -> bool:
        """Transient tunnel to check if a remote OPC UA endpoint is reachable.

        Opens a temporary SSH port forward, checks the local end, tears it down.
        """
        local_port = _find_free_port()
        parsed = urlparse(opc_url)
        remote_host = parsed.hostname or "localhost"
        remote_port = parsed.port or DEFAULT_OPC_PORT
        target = f"{ssh_user}@{ssh_host}" if ssh_user else ssh_host

        cmd = [
            "ssh", "-N", target,
            "-p", str(ssh_port),
            "-L", f"{local_port}:{remote_host}:{remote_port}",
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            "-o", "ExitOnForwardFailure=yes",
        ]
        logger.debug("ssh-ping: {}", " ".join(cmd))
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            for i in range(25):  # 25 * 0.2s = 5s
                if proc.returncode is not None:
                    stderr = ""
                    if proc.stderr:
                        data = await proc.stderr.read()
                        stderr = data.decode(errors="replace").strip()
                    logger.debug("ssh-ping exited {}: {}", proc.returncode, stderr)
                    return False
                try:
                    _, writer = await asyncio.open_connection("localhost", local_port)
                    writer.close()
                    await writer.wait_closed()
                    logger.debug("ssh-ping {} → {}:{} → online ({:.1f}s)", target, remote_host, remote_port, i * 0.2)
                    return True
                except (ConnectionRefusedError, OSError):
                    await asyncio.sleep(0.2)
            logger.debug("ssh-ping {} → timed out", target)
            return False
        except Exception as e:
            logger.debug("ssh-ping exception: {}", e)
            return False
        finally:
            if proc and proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except asyncio.TimeoutError:
                    proc.kill()
