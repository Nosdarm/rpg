import pytest
import sys # Import sys

# Запускаем pytest и сохраняем вывод в файл
original_stdout = sys.stdout # Save a reference to the original stdout
with open("test_results.txt", "w", encoding="utf-8") as f:
    sys.stdout = f # Redirect stdout to the file
    try:
        # Можно указать директорию или конкретные тесты
        pytest.main(["-v", "tests/", "--tb=short"]) # Remove stdout=f
    finally:
        sys.stdout = original_stdout # Restore stdout
