from anubis.cli.commands.agent import AGENT_COMMANDS
from anubis.cli.commands.execution import EXECUTION_COMMANDS
from anubis.cli.commands.system import SYSTEM_COMMANDS

SUPPORTED_COMMANDS = (*SYSTEM_COMMANDS, *EXECUTION_COMMANDS, *AGENT_COMMANDS)

__all__ = ["AGENT_COMMANDS", "EXECUTION_COMMANDS", "SUPPORTED_COMMANDS", "SYSTEM_COMMANDS"]
