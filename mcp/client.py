from __future__ import annotations
"""MCP (Model Context Protocol) client for managing tool integrations."""

import asyncio
import json
import subprocess
import sys
from typing import Any, Optional, Literal
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Type aliases
AgentType = Literal[
    "scheduler", "inbox", "routine", "shopping", "relationship", "concierge"
]
ServerName = Literal["gcal", "gmail", "tavily", "canva", "memory"]


class MCPClient:
    """Manages connections to MCP servers and tool invocations."""

    # Tool registry: maps agent types to their allowed MCP servers
    AGENT_TOOL_REGISTRY: dict[AgentType, list[ServerName]] = {
        "scheduler": ["gcal"],
        "inbox": ["gmail"],
        "routine": ["gcal", "memory"],
        "shopping": ["tavily", "memory"],
        "relationship": ["canva", "tavily", "memory"],
        "concierge": ["tavily", "gcal"],
    }

    def __init__(self, servers_config_path: Optional[str] = None, timeout: int = 30):
        """
        Initialize MCPClient with server configuration.

        Args:
            servers_config_path: Path to servers.json config (defaults to mcp/servers.json)
            timeout: Default timeout for tool calls (seconds)
        """
        self.servers_config_path = servers_config_path or "mcp/servers.json"
        self.timeout = timeout
        self.servers: dict[str, Any] = {}
        self.server_processes: dict[str, subprocess.Popen] = {}
        self.server_configs: dict[ServerName, dict] = {}
        self._load_server_configs()

    def _load_server_configs(self) -> None:
        """Load MCP server configurations from JSON file."""
        try:
            config_path = Path(self.servers_config_path)
            if config_path.exists():
                with open(config_path, "r") as f:
                    self.server_configs = json.load(f)
                logger.info(
                    "mcp_configs_loaded",
                    servers=list(self.server_configs.keys()),
                )
            else:
                logger.warning("mcp_config_file_not_found", path=self.servers_config_path)
        except Exception as e:
            logger.error("mcp_config_load_failed", error=str(e))
            raise

    async def connect(self, server_name: ServerName, config: Optional[dict] = None) -> None:
        """
        Connect to an MCP server.

        Args:
            server_name: Name of the server to connect to
            config: Optional configuration overrides

        Raises:
            ValueError: If server configuration not found
            Exception: If connection fails
        """
        try:
            # Get base config
            if server_name not in self.server_configs:
                raise ValueError(f"Server '{server_name}' not found in configuration")

            server_config = {**self.server_configs[server_name]}
            if config:
                server_config.update(config)

            # Resolve environment variables
            import os as _os
            env = {}
            if "env" in server_config:
                for key, value in server_config["env"].items():
                    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                        env_var = value[2:-1]
                        resolved = _os.getenv(env_var, "")
                        if not resolved:
                            logger.warning(
                                "mcp_env_var_not_set",
                                server=server_name,
                                env_var=env_var,
                            )
                        env[key] = resolved
                    else:
                        env[key] = value

            # Start server process
            command = server_config.get("command")
            args = server_config.get("args", [])

            full_command = [command] + args
            logger.debug(
                "mcp_server_starting",
                server=server_name,
                command=full_command,
            )

            process = subprocess.Popen(
                full_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**subprocess.os.environ, **env},
            )

            self.server_processes[server_name] = process
            self.servers[server_name] = {
                "process": process,
                "config": server_config,
                "connected": True,
            }

            logger.info(
                "mcp_server_connected",
                server=server_name,
                pid=process.pid,
            )

        except Exception as e:
            logger.error(
                "mcp_server_connection_failed",
                server=server_name,
                error=str(e),
            )
            raise

    async def disconnect(self, server_name: ServerName) -> None:
        """
        Disconnect from an MCP server.

        Args:
            server_name: Name of the server to disconnect
        """
        try:
            if server_name in self.server_processes:
                process = self.server_processes[server_name]
                process.terminate()

                # Wait for process to terminate
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

                del self.server_processes[server_name]
                if server_name in self.servers:
                    self.servers[server_name]["connected"] = False

                logger.info("mcp_server_disconnected", server=server_name)

        except Exception as e:
            logger.error(
                "mcp_server_disconnection_failed",
                server=server_name,
                error=str(e),
            )
            raise

    async def call_tool(
        self,
        server_name: ServerName,
        tool_name: str,
        arguments: dict[str, Any],
        timeout: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Call a tool on an MCP server.

        Args:
            server_name: MCP server name
            tool_name: Tool name to call
            arguments: Tool arguments
            timeout: Optional timeout override (seconds)

        Returns:
            Tool result dictionary

        Raises:
            ValueError: If server not connected
            TimeoutError: If tool call times out
            Exception: If tool execution fails
        """
        if server_name not in self.servers or not self.servers[server_name]["connected"]:
            raise ValueError(f"Server '{server_name}' not connected")

        timeout = timeout or self.timeout

        try:
            logger.debug(
                "mcp_tool_call_starting",
                server=server_name,
                tool=tool_name,
                arguments_keys=list(arguments.keys()),
            )

            process = self.server_processes[server_name]

            # Create request JSON for the tool
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }

            # Send request to server stdin
            request_json = json.dumps(request).encode() + b"\n"
            process.stdin.write(request_json) if process.stdin else None
            if process.stdin:
                process.stdin.flush()

            # Read response with timeout
            try:
                result_bytes = await asyncio.wait_for(
                    self._read_from_process(process),
                    timeout=timeout,
                )
                result = json.loads(result_bytes.decode())

                if "error" in result:
                    logger.error(
                        "mcp_tool_call_error",
                        server=server_name,
                        tool=tool_name,
                        error=result["error"],
                    )
                    raise Exception(f"Tool error: {result['error']}")

                logger.debug(
                    "mcp_tool_call_completed",
                    server=server_name,
                    tool=tool_name,
                )

                return result.get("result", {})

            except asyncio.TimeoutError:
                logger.error(
                    "mcp_tool_call_timeout",
                    server=server_name,
                    tool=tool_name,
                    timeout=timeout,
                )
                raise TimeoutError(
                    f"Tool call '{tool_name}' on '{server_name}' timed out after {timeout}s"
                )

        except Exception as e:
            logger.error(
                "mcp_tool_call_failed",
                server=server_name,
                tool=tool_name,
                error=str(e),
            )
            raise

    async def list_tools(self, server_name: ServerName) -> list[dict]:
        """
        List available tools from an MCP server.

        Args:
            server_name: MCP server name

        Returns:
            List of tool definitions

        Raises:
            ValueError: If server not connected
        """
        if server_name not in self.servers or not self.servers[server_name]["connected"]:
            raise ValueError(f"Server '{server_name}' not connected")

        try:
            logger.debug("mcp_listing_tools", server=server_name)

            process = self.server_processes[server_name]

            # Create request for tools/list
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
            }

            request_json = json.dumps(request).encode() + b"\n"
            process.stdin.write(request_json) if process.stdin else None
            if process.stdin:
                process.stdin.flush()

            # Read response
            result_bytes = await asyncio.wait_for(
                self._read_from_process(process),
                timeout=self.timeout,
            )
            result = json.loads(result_bytes.decode())

            tools = result.get("result", {}).get("tools", [])
            logger.info("mcp_tools_listed", server=server_name, count=len(tools))

            return tools

        except Exception as e:
            logger.error(
                "mcp_list_tools_failed",
                server=server_name,
                error=str(e),
            )
            raise

    def get_tools_for_agent(self, agent_name: AgentType) -> dict[ServerName, list[str]]:
        """
        Get available MCP servers and tools for a given agent type.

        Args:
            agent_name: Type of agent (scheduler, inbox, routine, etc.)

        Returns:
            Dictionary mapping server names to their tools
        """
        try:
            allowed_servers = self.AGENT_TOOL_REGISTRY.get(agent_name, [])

            if not allowed_servers:
                logger.warning("agent_has_no_tools", agent=agent_name)
                return {}

            # In a real implementation, you'd dynamically fetch tools from each server
            # For now, return the server names (actual tool lists fetched at runtime)
            tools_by_server: dict[ServerName, list[str]] = {}

            for server_name in allowed_servers:
                if server_name in self.servers and self.servers[server_name]["connected"]:
                    # Placeholder: actual tool list would be fetched from server
                    tools_by_server[server_name] = []

            logger.debug(
                "agent_tools_retrieved",
                agent=agent_name,
                servers=allowed_servers,
            )

            return tools_by_server

        except Exception as e:
            logger.error(
                "get_tools_for_agent_failed",
                agent=agent_name,
                error=str(e),
            )
            raise

    @staticmethod
    async def _read_from_process(process: subprocess.Popen) -> bytes:
        """
        Read output from subprocess asynchronously.

        Args:
            process: Subprocess to read from

        Returns:
            Output bytes
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, process.stdout.readline)

    async def close_all(self) -> None:
        """Close all server connections."""
        server_names = list(self.server_processes.keys())
        for server_name in server_names:
            try:
                await self.disconnect(server_name)
            except Exception as e:
                logger.error(
                    "close_server_error",
                    server=server_name,
                    error=str(e),
                )

        logger.info("mcp_client_closed")

    def __repr__(self) -> str:
        """String representation of MCPClient."""
        connected = [s for s, v in self.servers.items() if v.get("connected")]
        return (
            f"MCPClient(connected_servers={connected}, "
            f"timeout={self.timeout}s)"
        )
