import sys
import os

# Add the project root to sys.path to allow imports from src
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from pydantic import ValidationError

from src.models.command_info import (
    CommandParameterInfo,
    CommandInfo,
    CommandListResponse
)

def test_command_parameter_info_creation():
    param_info = CommandParameterInfo(
        name="amount",
        description="The amount to transfer.",
        type="integer",
        required=True
    )
    assert param_info.name == "amount"
    assert param_info.description == "The amount to transfer."
    assert param_info.type == "integer"
    assert param_info.required is True

def test_command_parameter_info_optional_description():
    param_info = CommandParameterInfo(
        name="target",
        description=None, # Explicitly pass None for optional field
        type="user",
        required=False
    )
    assert param_info.name == "target"
    assert param_info.description is None
    assert param_info.type == "user"
    assert param_info.required is False

def test_command_info_creation():
    param1 = CommandParameterInfo(name="param1", type="string", required=True)
    cmd_info = CommandInfo(
        name="mycommand",
        description="This is a test command.",
        parameters=[param1]
    )
    assert cmd_info.name == "mycommand"
    assert cmd_info.description == "This is a test command."
    assert len(cmd_info.parameters) == 1
    assert cmd_info.parameters[0].name == "param1"

def test_command_info_no_parameters_no_description():
    cmd_info = CommandInfo(name="simplecmd", description=None) # Explicitly pass None
    assert cmd_info.name == "simplecmd"
    assert cmd_info.description is None
    assert cmd_info.parameters == []

def test_command_list_response_creation():
    cmd1 = CommandInfo(name="cmd1", description=None) # Explicitly pass None
    cmd2 = CommandInfo(name="cmd2", description="A second command.")
    response = CommandListResponse(
        commands=[cmd1, cmd2],
        language_code="en"
    )
    assert len(response.commands) == 2
    assert response.commands[0].name == "cmd1"
    assert response.commands[1].name == "cmd2"
    assert response.language_code == "en"

def test_command_list_response_empty_commands():
    response = CommandListResponse(commands=[], language_code="ru")
    assert response.commands == []
    assert response.language_code == "ru"

def test_command_list_response_no_language_code():
    response = CommandListResponse(commands=[CommandInfo(name="cmd", description=None)]) # Explicitly pass None
    assert response.language_code is None

# Пример теста на валидацию, если бы были более строгие правила
# def test_command_parameter_info_missing_required_field():
#     with pytest.raises(ValidationError):
#         # Assuming 'name' is absolutely required and has no default
#         CommandParameterInfo(type="string", required=True)
#
#     with pytest.raises(ValidationError):
#         CommandInfo() # Assuming 'name' is required for CommandInfo
#
#     with pytest.raises(ValidationError):
#         CommandListResponse() # Assuming 'commands' is required
#
# Эти тесты не пройдут с текущими моделями, так как Pydantic
# будет жаловаться на отсутствие полей еще до создания экземпляра,
# если у них нет значений по умолчанию.
# Для полей с default или default_factory ValidationError не будет.
# Например, CommandInfo(name="cmd") создастся успешно, description и parameters будут по умолчанию.

# Проверка, что поля действительно обязательны, если нет default
# class TestStrictModels:
#     def test_param_info_strict(self):
#         with pytest.raises(ValidationError) as excinfo:
#             CommandParameterInfo() # name, type, required не имеют default
#         # Проверка, что ошибка именно из-за этих полей
#         assert "'name' is a required field" in str(excinfo.value) # Пример
#         assert "'type' is a required field" in str(excinfo.value)
#         assert "'required' is a required field" in str(excinfo.value)

# У Pydantic v2 поля без Optional и без default являются обязательными.
# Текущие модели имеют аннотации, и Pydantic это учтет.
# Например, CommandParameterInfo(name="test", type="str", required=True) - валидно.
# CommandParameterInfo(name="test", type="str") - невалидно, т.к. required отсутствует.

def test_command_parameter_info_validation_error():
    with pytest.raises(ValidationError):
        CommandParameterInfo(name="test", type="str") # 'required' is missing, description is optional

    with pytest.raises(ValidationError):
        CommandParameterInfo(name="test", required=True) # 'type' is missing, description is optional

    with pytest.raises(ValidationError):
        CommandParameterInfo(type="str", required=True) # 'name' is missing, description is optional

def test_command_info_validation_error():
    with pytest.raises(ValidationError):
        CommandInfo(description="test") # 'name' is missing, parameters is optional (defaults to [])

def test_command_list_response_validation_error():
    with pytest.raises(ValidationError):
        CommandListResponse(language_code="en") # 'commands' is missing, language_code is optional

# Corrected tests based on pyright feedback for genuinely missing fields
def test_command_parameter_info_actually_missing_fields():
    with pytest.raises(ValidationError, match="required"): # Expecting error about 'required'
        CommandParameterInfo(name="test", type="str")

    with pytest.raises(ValidationError, match="type"): # Expecting error about 'type'
        CommandParameterInfo(name="test", required=True)

    with pytest.raises(ValidationError, match="name"): # Expecting error about 'name'
        CommandParameterInfo(type="str", required=True)

def test_command_info_actually_missing_fields():
    with pytest.raises(ValidationError, match="name"): # Expecting error about 'name'
        CommandInfo(description="A command that is missing its name.")

def test_command_list_response_actually_missing_fields():
    with pytest.raises(ValidationError, match="commands"): # Expecting error about 'commands'
        CommandListResponse(language_code="en")


# The pytest.main() call is unusual for typical test suite execution.
# It's often run by a test runner like `pytest` from the command line.
# Removing it as it might cause issues in some environments or if this file is imported.
# pytest.main()
