"""SSH tunnel manager — port-forward remote OPC UA endpoints.

Creates an SSH tunnel (ssh -L) to forward a local port to the remote
OPC UA server, so the client can connect via localhost.
"""

import asyncio
import os
import random
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

from loguru import logger

from opguia.utils import DEFAULT_OPC_PORT, EPHEMERAL_PORT_RANGE


def _find_free_port() -> int:
    """Pick a random high port that's likely free."""
    return random.randint(*EPHEMERAL_PORT_RANGE)


def _make_askpass(password: str) -> tuple[str, dict]:
    """Create a temporary askpass script and env dict for SSH password auth.

    Returns (script_path, env_dict).
    """
    env = os.environ.copy()
    env["_OPGUIA_SSH_PASS"] = password
    env["SSH_ASKPASS_REQUIRE"] = "force"

    if sys.platform == "win32":
        fd, path = tempfile.mkstemp(suffix=".bat")
        with os.fdopen(fd, "w") as f:
            f.write("@echo off\necho %_OPGUIA_SSH_PASS%\n")
    else:
        fd, path = tempfile.mkstemp(suffix=".sh")
        with os.fdopen(fd, "w") as f:
            f.write('#!/bin/sh\necho "$_OPGUIA_SSH_PASS"\n')
        os.chmod(path, stat.S_IRWXU)

    env["SSH_ASKPASS"] = path
    return path, env


def _cleanup_askpass(path: str | None):
    """Remove a temporary askpass script."""
    if path:
        try:
            os.unlink(path)
        except OSError:
            pass


class SSHTunnel:
    """Manages a single SSH port-forwarding tunnel."""

    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self.local_port: int | None = None
        self._askpass_file: str | None = None

    @property
    def active(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self, opc_url: str, ssh_host: str, ssh_user: str = "",
                    ssh_port: int = 22, ssh_password: str = "") -> str:
        """Start an SSH tunnel and return the local OPC UA URL.

        Args:
            opc_url:  Original OPC UA endpoint (e.g. opc.tcp://192.168.1.10:4840)
            ssh_host: SSH server hostname/IP to tunnel through
            ssh_user: SSH username (optional, uses system default if empty)
            ssh_port: SSH port (default 22)
            ssh_password: SSH password (optional, uses key-based auth if empty)

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

        # Set up password auth via SSH_ASKPASS if password provided
        extra_kwargs: dict = {}
        _cleanup_askpass(self._askpass_file)
        self._askpass_file = None
        if ssh_password:
            self._askpass_file, extra_kwargs["env"] = _make_askpass(ssh_password)
            if sys.platform == "win32":
                extra_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                extra_kwargs["start_new_session"] = True

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            **extra_kwargs,
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
        _cleanup_askpass(self._askpass_file)
        self._askpass_file = None

    @staticmethod
    async def ping(opc_url: str, ssh_host: str, ssh_user: str = "",
                   ssh_port: int = 22, ssh_password: str = "") -> bool:
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
            "-o", "ExitOnForwardFailure=yes",
        ]
        # Use BatchMode (no password prompt) unless we have a password
        askpass_file = None
        extra_kwargs: dict = {}
        if ssh_password:
            askpass_file, extra_kwargs["env"] = _make_askpass(ssh_password)
            if sys.platform == "win32":
                extra_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                extra_kwargs["start_new_session"] = True
        else:
            cmd += ["-o", "BatchMode=yes"]

        logger.debug("ssh-ping: {}", " ".join(cmd))
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                **extra_kwargs,
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
            _cleanup_askpass(askpass_file)
