from typing import List, Optional

from pydantic import BaseModel, Field


class CommandParameterInfo(BaseModel):
    name: str = Field(description="Parameter name.")
    description: Optional[str] = Field(None, description="Parameter description.")
    type: str = Field(description="Parameter type (e.g., 'string', 'integer', 'boolean', 'user', 'channel').")
    required: bool = Field(description="Whether the parameter is required.")
    # TODO: Add localized descriptions if available/needed
    # TODO: Consider choices for parameters


class CommandInfo(BaseModel):
    name: str = Field(description="Command name.")
    description: Optional[str] = Field(None, description="Command description.")
    parameters: List[CommandParameterInfo] = Field(default_factory=list, description="List of command parameters.")
    # permissions: Optional[List[str]] = Field(None, description="Permissions required to use the command.")
    # TODO: Add localized name/description if available/needed
    # TODO: Consider how to represent subcommands/groups
    # TODO: Add information about whether the command is guild_only or global


class CommandListResponse(BaseModel):
    commands: List[CommandInfo] = Field(description="List of available bot commands.")
    language_code: Optional[str] = Field(None, description="Language code of the returned information (e.g., 'en', 'ru').")
