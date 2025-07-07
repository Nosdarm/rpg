# This directory will contain individual Cogs for master commands,
# broken down by entity or functional area.
# Example: player_master_commands.py, ruleconfig_master_commands.py, etc.

# For now, this __init__.py can remain empty or be used later
# if a helper function to load all cogs from this directory is needed.
# Example of potential future use (not implemented now):
#
# from pathlib import Path
#
# def load_master_commands_cogs():
#     cog_files = [f.stem for f in Path(__file__).parent.glob("*.py") if f.name != "__init__.py"]
#     return [f"src.bot.commands.master_commands.{cog_file}" for cog_file in cog_files]
#
# MASTER_COMMAND_COGS = load_master_commands_cogs()

# Individual cogs will be added to BOT_COGS in settings.py directly.
# e.g., "src.bot.commands.master_commands.player_master_commands"
pass
