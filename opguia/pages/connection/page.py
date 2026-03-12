"""Connection page — endpoint input, server scan, connect.

Landing page at "/". Two-column layout: left has manual input + discovered
servers, right has saved profiles with status pings and connect buttons.
"""

import asyncio
import socket
from urllib.parse import urlparse
from loguru import logger
from nicegui import ui
from opguia.client import OpcuaClient
from opguia.scanner import scan_servers
from opguia.storage import Settings
from opguia.theme import apply_theme
from opguia.tunnel import SSHTunnel
from opguia.ui_base import PageContext
from opguia.utils import DEFAULT_OPC_PORT


def _ping_sync(url: str, timeout: float = 2.0) -> bool:
    """Synchronous TCP check (runs in a thread to avoid NiceGUI future conflicts)."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or DEFAULT_OPC_PORT
        with socket.create_connection((host, port), timeout=timeout):
            logger.debug("ping {}:{} → online", host, port)
            return True
    except Exception as e:
        logger.debug("ping {} → failed: {}", url, e)
        return False


async def _ping(url: str, timeout: float = 2.0) -> bool:
    """Quick TCP check to see if an OPC UA endpoint is reachable."""
    return await asyncio.to_thread(_ping_sync, url, timeout)


def _ssh_preview(opc_url: str, ssh_host: str, ssh_user: str = "", ssh_port: str = "22") -> str:
    """Generate SSH command preview string for display."""
    parsed = urlparse(opc_url)
    rh = parsed.hostname or "localhost"
    rp = parsed.port or DEFAULT_OPC_PORT
    target = f"{ssh_user}@{ssh_host}" if ssh_user else ssh_host
    port_flag = f" -p {ssh_port}" if ssh_port != "22" else ""
    return f"ssh {target} -L <port>:{rh}:{rp}{port_flag}"


def register(client: OpcuaClient, settings: Settings, tunnel: SSHTunnel = None):
    _tunnel = tunnel or SSHTunnel()

    @ui.page("/")
    async def connection_page():
        apply_theme()
        ctx = PageContext()

        # ── Header ──
        with ui.row().classes("w-full items-center justify-center gap-3 py-6 shrink-0"):
            ui.image("/static/favicon.svg").classes("w-10 h-10")
            with ui.column().classes("gap-0"):
                ui.label("OPGuia").classes("text-3xl font-bold")
                ui.label("OPC UA Browser").classes("text-xs text-gray-400 -mt-1")

        # ── Two-column layout ──
        with ui.row().classes(
            "w-full justify-center no-wrap gap-6 px-6"
        ).style("flex:1; min-height:0; overflow:hidden"):

            # ── Left column: manual + discovered ──
            with ui.column().classes("gap-4").style("width:400px; overflow-y:auto"):

                # Manual endpoint input
                with ui.card().classes("w-full p-4"):
                    ui.label("Manual Connection").classes("text-sm font-bold")
                    endpoint = ui.input(
                        "Endpoint", value="opc.tcp://localhost:4840"
                    ).classes("w-full mt-2")
                    profile_name = ui.input("Profile name", value="").props("dense").classes(
                        "w-full"
                    ).style("font-size:12px")
                    profile_name.props('placeholder="Optional — uses server name"')

                    # SSH tunnel options
                    with ui.expansion("SSH Port Forward", icon="lan").classes(
                        "w-full"
                    ).style("font-size:12px") as tunnel_exp:
                        tunnel_exp.props("dense")
                        with ui.column().classes("w-full gap-2 py-1"):
                            tunnel_toggle = ui.switch("Enable SSH tunnel").props("dense")
                            tunnel_host = ui.input("SSH Host").props("dense").classes("w-full")
                            tunnel_host.props('placeholder="e.g. gateway.example.com"')
                            with ui.row().classes("w-full gap-2"):
                                tunnel_user = ui.input("SSH User").props("dense").classes("flex-grow")
                                tunnel_user.props('placeholder="Optional"')
                                tunnel_port = ui.input("SSH Port", value="22").props(
                                    "dense type=number"
                                ).style("width:80px")
                            tunnel_password = ui.input(
                                "SSH Password", password=True, password_toggle_button=True,
                            ).props("dense").classes("w-full")
                            tunnel_password.props('placeholder="Leave empty for key-based auth"')
                            # Live command preview
                            tunnel_preview = ui.label("").classes(
                                "text-xs font-mono text-gray-500 break-all"
                            )
                            tunnel_preview.style("display:none")

                            def _update_preview():
                                if not tunnel_toggle.value or not tunnel_host.value.strip():
                                    tunnel_preview.style("display:none")
                                    return
                                tunnel_preview.style(replace="display:block")
                                tunnel_preview.text = _ssh_preview(
                                    endpoint.value, tunnel_host.value.strip(),
                                    tunnel_user.value.strip(),
                                    (tunnel_port.value or "").strip() or "22",
                                )

                            for _inp in (tunnel_toggle, tunnel_host, tunnel_user, tunnel_port, endpoint):
                                _inp.on("update:model-value", lambda: _update_preview())

                    status = ui.label("").classes("text-xs")

                    async def do_connect():
                        connect_btn.props("loading")
                        status.text = "Connecting..."
                        status.classes(remove="text-red-400 text-green-400")
                        try:
                            url = endpoint.value
                            if tunnel_toggle.value and tunnel_host.value.strip():
                                status.text = "Starting SSH tunnel..."
                                url = await _tunnel.start(
                                    url,
                                    ssh_host=tunnel_host.value.strip(),
                                    ssh_user=tunnel_user.value.strip(),
                                    ssh_port=int(tunnel_port.value or 22),
                                    ssh_password=tunnel_password.value or "",
                                )
                                status.text = f"Tunnel up → {url}. Connecting..."
                            await client.connect(url)
                            name = profile_name.value.strip() or client.server_name or endpoint.value
                            settings.ensure_profile(endpoint.value, name)
                            # Save tunnel settings to profile
                            prof = settings._find_profile(endpoint.value)
                            if prof:
                                prof["tunnel_enabled"] = bool(tunnel_toggle.value)
                                prof["tunnel_ssh_host"] = tunnel_host.value.strip()
                                prof["tunnel_ssh_user"] = tunnel_user.value.strip()
                                prof["tunnel_ssh_port"] = int(tunnel_port.value or 22)
                                prof["tunnel_ssh_password"] = tunnel_password.value or ""
                                settings._save()
                            settings.set_active(endpoint.value)
                            status.text = "Connected"
                            status.classes(add="text-green-400")
                            await asyncio.sleep(0.3)
                            ui.navigate.to("/browse")
                        except Exception as e:
                            await _tunnel.stop()
                            status.text = str(e)
                            status.classes(add="text-red-400")
                        finally:
                            connect_btn.props(remove="loading")

                    with ui.row().classes("w-full gap-2"):
                        connect_btn = ui.button("Connect", on_click=do_connect).classes("flex-grow")
                        ui.button(
                            icon="bookmark_add",
                            on_click=lambda: save_profile(endpoint.value, profile_name.value.strip()),
                        ).props("flat dense").tooltip("Save profile")

                # Discovered servers
                with ui.card().classes("w-full p-4"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label("Discovered Servers").classes("text-sm font-bold")
                        scan_spinner = ui.spinner(size="sm")
                    scan_list = ui.column().classes("w-full gap-1 mt-2")

                    _discovered_urls: set[str] = set()

                    async def run_scan():
                        scan_spinner.visible = True
                        servers = await scan_servers()
                        scan_spinner.visible = False
                        # Only update if the set of URLs actually changed
                        new_urls = {s["url"] for s in servers}
                        if new_urls == _discovered_urls:
                            return
                        _discovered_urls.clear()
                        _discovered_urls.update(new_urls)
                        scan_list.clear()
                        with scan_list:
                            if not servers:
                                ui.label("No servers found").classes("text-xs text-gray-500")
                            for srv in servers:
                                with ui.row().classes(
                                    "items-center gap-2 w-full hover:bg-gray-800 rounded px-2 py-1 cursor-pointer"
                                ) as row:
                                    ui.icon("dns", size="14px").classes("text-green-400")
                                    with ui.column().classes("gap-0"):
                                        ui.label(srv["name"] or "OPC UA Server").classes(
                                            "text-xs font-bold"
                                        )
                                        ui.label(srv["url"]).classes(
                                            "text-xs text-gray-400 font-mono"
                                        )

                                    def pick(url=srv["url"], name=srv["name"]):
                                        endpoint.value = url
                                        if name:
                                            profile_name.value = name
                                    row.on("click", pick)

                    ctx.spawn(run_scan())
                    ctx.timer(5.0, run_scan)

                # Show existing connection if already connected
                if client.connected:
                    with ui.row().classes("items-center gap-1"):
                        ui.icon("check_circle", size="xs").classes("text-green-400")
                        ui.label(client.endpoint).classes("text-xs text-green-400")
                        ui.button(
                            "Browse", on_click=lambda: ui.navigate.to("/browse")
                        ).props("flat dense size=sm")

            # ── Right column: saved profiles ──
            with ui.column().classes("gap-0").style("width:400px; overflow-y:auto"):
                saved_card = ui.card().classes("w-full p-4")

                async def _do_connect_profile(url: str, name: str, btn=None, prof=None,
                                              ssh_password: str = ""):
                    if btn:
                        btn.props("loading")
                    try:
                        connect_url = url
                        if prof and prof.get("tunnel_enabled") and prof.get("tunnel_ssh_host"):
                            connect_url = await _tunnel.start(
                                url,
                                ssh_host=prof["tunnel_ssh_host"],
                                ssh_user=prof.get("tunnel_ssh_user", ""),
                                ssh_port=prof.get("tunnel_ssh_port", 22),
                                ssh_password=ssh_password,
                            )
                            prof["tunnel_ssh_password"] = ssh_password
                            settings._save()
                        await client.connect(connect_url)
                        settings.ensure_profile(url, name)
                        settings.set_active(url)
                        ui.navigate.to("/browse")
                    except Exception as e:
                        await _tunnel.stop()
                        ui.notify(str(e), type="negative")
                    finally:
                        if btn:
                            btn.props(remove="loading")

                async def connect_profile(url: str, name: str, btn=None, prof=None):
                    if prof and prof.get("tunnel_enabled") and prof.get("tunnel_ssh_host"):
                        # Prompt for SSH password before connecting
                        with ui.dialog() as dlg, ui.card().classes("p-4").style("min-width:340px"):
                            ui.label("SSH Password").classes("text-sm font-bold mb-1")
                            ssh_target = prof.get("tunnel_ssh_user", "")
                            ssh_target = (ssh_target + "@" if ssh_target else "") + prof["tunnel_ssh_host"]
                            ui.label(ssh_target).classes("text-xs font-mono text-gray-400 mb-2")
                            pw_input = ui.input(
                                "Password", password=True, password_toggle_button=True,
                                value=prof.get("tunnel_ssh_password", ""),
                            ).props("dense").classes("w-full")
                            pw_input.props('placeholder="Leave empty for key-based auth"')
                            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                                ui.button("Cancel", on_click=dlg.close).props("flat dense")

                                async def _on_connect():
                                    dlg.close()
                                    await _do_connect_profile(
                                        url, name, btn, prof,
                                        ssh_password=pw_input.value or "",
                                    )

                                ui.button("Connect", on_click=_on_connect).props("dense color=primary")
                            pw_input.on("keydown.enter", _on_connect)
                        dlg.open()
                    else:
                        await _do_connect_profile(url, name, btn, prof)

                def render_saved():
                    saved_card.clear()
                    with saved_card:
                        ui.label("Saved Profiles").classes("text-sm font-bold mb-2")
                        profiles = settings.profiles
                        if not profiles:
                            ui.label("No saved profiles yet").classes(
                                "text-xs text-gray-500 mt-1"
                            )
                            ui.label(
                                "Connect to a server and click the bookmark icon to save."
                            ).classes("text-xs text-gray-600 mt-1")
                        else:
                            with ui.column().classes("w-full gap-2"):
                                for prof in profiles:
                                    _render_profile_row(prof)

                def _edit_profile_dialog(prof):
                    """Open a modal dialog to edit all profile fields."""
                    with ui.dialog() as dlg, ui.card().classes("p-4").style("min-width:380px"):
                        ui.label("Edit Profile").classes("text-sm font-bold mb-2")

                        ed_name = ui.input("Name", value=prof["name"]).classes("w-full")
                        ed_url = ui.input("Endpoint URL", value=prof["url"]).classes("w-full")

                        ui.separator().classes("my-2")
                        ui.label("SSH Port Forward").classes("text-xs font-bold text-gray-400")

                        ed_tunnel = ui.switch(
                            "Enable SSH tunnel", value=prof.get("tunnel_enabled", False)
                        ).props("dense")
                        ed_ssh_host = ui.input(
                            "SSH Host", value=prof.get("tunnel_ssh_host", "")
                        ).props("dense").classes("w-full")
                        ed_ssh_host.props('placeholder="e.g. gateway.example.com"')
                        with ui.row().classes("w-full gap-2"):
                            ed_ssh_user = ui.input(
                                "SSH User", value=prof.get("tunnel_ssh_user", "")
                            ).props("dense").classes("flex-grow")
                            ed_ssh_user.props('placeholder="Optional"')
                            ed_ssh_port = ui.input(
                                "SSH Port", value=str(prof.get("tunnel_ssh_port", 22))
                            ).props("dense type=number").style("width:80px")
                        ed_ssh_password = ui.input(
                            "SSH Password", password=True, password_toggle_button=True,
                            value=prof.get("tunnel_ssh_password", ""),
                        ).props("dense").classes("w-full")
                        ed_ssh_password.props('placeholder="Leave empty for key-based auth"')

                        # Live command preview
                        ed_preview = ui.label("").classes(
                            "text-xs font-mono text-gray-500 break-all"
                        )
                        ed_preview.style("display:none")

                        def _update_ed_preview():
                            if not ed_tunnel.value or not ed_ssh_host.value.strip():
                                ed_preview.style("display:none")
                                return
                            ed_preview.style(replace="display:block")
                            ed_preview.text = _ssh_preview(
                                ed_url.value, ed_ssh_host.value.strip(),
                                ed_ssh_user.value.strip(),
                                (ed_ssh_port.value or "").strip() or "22",
                            )

                        for _inp in (ed_tunnel, ed_ssh_host, ed_ssh_user, ed_ssh_port, ed_url):
                            _inp.on("update:model-value", lambda: _update_ed_preview())
                        _update_ed_preview()  # show preview if already configured

                        ui.separator().classes("my-2")

                        with ui.row().classes("w-full justify-end gap-2"):
                            ui.button("Cancel", on_click=dlg.close).props("flat dense")

                            def save_edits():
                                old_url = prof["url"]
                                prof["name"] = ed_name.value.strip() or prof["name"]
                                prof["url"] = ed_url.value.strip() or prof["url"]
                                prof["tunnel_enabled"] = bool(ed_tunnel.value)
                                prof["tunnel_ssh_host"] = ed_ssh_host.value.strip()
                                prof["tunnel_ssh_user"] = ed_ssh_user.value.strip()
                                prof["tunnel_ssh_port"] = int(ed_ssh_port.value or 22)
                                prof["tunnel_ssh_password"] = ed_ssh_password.value or ""
                                settings._save()
                                dlg.close()
                                render_saved()

                            ui.button("Save", on_click=save_edits).props("dense color=primary")

                    dlg.open()

                def _render_profile_row(prof):
                    with ui.card().classes("w-full p-3").props("flat bordered"):
                        with ui.row().classes("items-start gap-3 w-full"):
                            # Status dot
                            dot = ui.icon("circle", size="10px").classes(
                                "text-gray-600 shrink-0 mt-1"
                            )

                            with ui.column().classes("gap-1 min-w-0 flex-grow"):
                                with ui.row().classes("items-center gap-1 w-full"):
                                    ui.label(prof["name"]).classes(
                                        "text-sm font-medium truncate"
                                    )

                                ui.label(prof["url"]).classes(
                                    "font-mono text-gray-500 truncate"
                                ).style("font-size:11px")

                                # Stats row
                                with ui.row().classes("items-center gap-3 mt-1"):
                                    watched_count = len(prof.get("watched", []))
                                    if watched_count:
                                        with ui.row().classes("items-center gap-1"):
                                            ui.icon("visibility", size="12px").classes(
                                                "text-blue-400"
                                            )
                                            ui.label(
                                                f"{watched_count} watched"
                                            ).classes("text-xs text-gray-400")

                                    root_path = prof.get("tree_root_path", [])
                                    if root_path:
                                        with ui.row().classes("items-center gap-1"):
                                            ui.icon("folder", size="12px").classes(
                                                "text-yellow-500"
                                            )
                                            ui.label(
                                                " / ".join(root_path[-2:])
                                            ).classes("text-xs text-gray-400 truncate")

                                    if prof.get("tunnel_enabled") and prof.get("tunnel_ssh_host"):
                                        with ui.row().classes("items-center gap-1"):
                                            ui.icon("lan", size="12px").classes(
                                                "text-cyan-400"
                                            )
                                            ssh_label = prof.get("tunnel_ssh_user", "")
                                            ssh_label = (ssh_label + "@" if ssh_label else "") + prof["tunnel_ssh_host"]
                                            ui.label(
                                                f"via {ssh_label}"
                                            ).classes("text-xs text-gray-400 truncate")

                                    status_label = ui.label("Checking...").classes(
                                        "text-xs text-gray-600"
                                    )

                        with ui.row().classes("w-full justify-end gap-1 mt-2"):
                            prof_btn = ui.button("Connect").props("dense size=sm color=primary")
                            prof_btn.on(
                                "click",
                                lambda u=prof["url"], n=prof["name"], b=prof_btn, p=prof: connect_profile(u, n, b, p),
                            )

                            ui.button(
                                icon="edit",
                                on_click=lambda p=prof: _edit_profile_dialog(p),
                            ).props("flat dense size=sm").tooltip("Edit profile")

                            def remove(u=prof["url"]):
                                settings.remove_profile(u)
                                render_saved()

                            ui.button(
                                icon="delete", on_click=remove,
                            ).props("flat dense size=sm color=red").tooltip("Remove profile")

                    # Continuous ping via ui.timer (holds a strong reference, preventing GC)
                    use_ssh = prof.get("tunnel_enabled") and prof.get("tunnel_ssh_host")
                    ping_interval = 30.0 if use_ssh else 10.0

                    _ping_running = False

                    async def do_ping(url=prof["url"], d=dot, btn=prof_btn, lbl=status_label, p=prof):
                        nonlocal _ping_running
                        if _ping_running:
                            return
                        _ping_running = True
                        try:
                            if p.get("tunnel_enabled") and p.get("tunnel_ssh_host"):
                                reachable = await SSHTunnel.ping(
                                    url,
                                    ssh_host=p["tunnel_ssh_host"],
                                    ssh_user=p.get("tunnel_ssh_user", ""),
                                    ssh_port=p.get("tunnel_ssh_port", 22),
                                    ssh_password=p.get("tunnel_ssh_password", ""),
                                )
                            else:
                                reachable = await _ping(url)
                            if reachable:
                                d.classes(remove="text-gray-600 text-red-500", add="text-green-500")
                                lbl.text = "Online"
                                lbl.classes(remove="text-gray-600 text-red-500", add="text-green-500")
                                btn.props(remove="disable")
                            else:
                                d.classes(remove="text-gray-600 text-green-500", add="text-red-500")
                                lbl.text = "Unreachable"
                                lbl.classes(remove="text-gray-600 text-green-500", add="text-red-500")
                                btn.props("disable")
                        except Exception:
                            pass  # UI elements may have been destroyed by render_saved()
                        finally:
                            _ping_running = False

                    ui.timer(ping_interval, do_ping)
                    ui.timer(0.1, do_ping, once=True)  # immediate first ping

                render_saved()

                def save_profile(url: str, name: str = ""):
                    settings.add_profile(name or url, url)
                    render_saved()
