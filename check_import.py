import sys
import pydantic
import pydantic_settings

print("Python Executable:", sys.executable)
print("Python Version:", sys.version)
print("Pydantic Version:", pydantic.__version__)
print("Pydantic-Settings Loaded from:", pydantic_settings.__file__)

try:
    from pydantic_settings import BaseSettings
    print("BaseSettings successfully imported from pydantic_settings")
except ImportError as e:
    print(f"Error importing BaseSettings from pydantic_settings: {e}")

try:
    from backend.config.settings import settings
    print("Backend settings loaded successfully.")
    print(settings)
except Exception as e:
    print(f"Error loading backend settings: {e}")
