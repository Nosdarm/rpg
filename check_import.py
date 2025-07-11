import sys
print("--- Attempting import from check_import.py ---")
print(f"Current sys.path: {sys.path}")
print(f"Current working directory: {__import__('os').getcwd()}")

try:
    import backend.core.global_entity_manager
    print("SUCCESS: import src.core.global_entity_manager worked!")
except ImportError as e:
    print(f"FAIL (ImportError): {e}")
except Exception as e:
    print(f"FAIL (Other Exception): {e}")

print("--- Finished import attempt from check_import.py ---")
