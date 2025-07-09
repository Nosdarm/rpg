import pytest

# Запускаем pytest и сохраняем вывод в файл
with open("test_results.txt", "w", encoding="utf-8") as f:
    # Можно указать директорию или конкретные тесты
    pytest.main(["-v", "tests/", "--tb=short"], stdout=f)
