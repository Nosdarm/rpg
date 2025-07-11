from typing import List, Optional, Dict, Any # Added Dict, Any

from pydantic import BaseModel, Field


class CommandParameterInfo(BaseModel):
    name: str = Field(description="Parameter name.")
    description: Optional[str] = Field(None, description="Parameter description.")
    type: str = Field(description="Parameter type (e.g., 'string', 'integer', 'boolean', 'user', 'channel').")
    required: bool = Field(description="Whether the parameter is required.")
    choices: Optional[List[Dict[str, Any]]] = Field(None, description="List of available choices for the parameter, if any. Each choice is a dict with 'name' and 'value'.")
    # TODO: Add localized descriptions if available/needed


class CommandInfo(BaseModel):
    name: str = Field(description="Command name.")
    description: Optional[str] = Field(None, description="Command description.")
    parameters: List[CommandParameterInfo] = Field(default_factory=list, description="List of command parameters.")
    guild_only: Optional[bool] = Field(None, description="Whether the command is usable only in guilds (servers).")
    nsfw: Optional[bool] = Field(None, description="Whether the command is Not Safe For Work.")
    dm_permission: Optional[bool] = Field(None, description="Whether the command is usable in DMs.")
    # permissions: Optional[List[str]] = Field(None, description="Permissions required to use the command.")
    # TODO: Add localized name/description if available/needed
    # TODO: Consider how to represent subcommands/groups


class CommandListResponse(BaseModel):
    commands: List[CommandInfo] = Field(description="List of available bot commands.")
    language_code: Optional[str] = Field(None, description="Language code of the returned information (e.g., 'en', 'ru').")
