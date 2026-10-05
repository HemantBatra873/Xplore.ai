"""
Local LLM tool unit tests (get_current_weather, get_system_status)
"""

from app.services.llm_service import get_current_weather, get_system_status


class TestWeatherTool:
    def test_known_city_beijing(self):
        result = get_current_weather("Beijing")
        assert "Clear" in result
        assert "25 C" in result

    def test_known_city_shanghai(self):
        result = get_current_weather("Shanghai")
        assert "Cloudy" in result
        assert "28 C" in result

    def test_known_city_guangzhou(self):
        result = get_current_weather("Guangzhou")
        assert "Light rain" in result
        assert "26 C" in result

    def test_unknown_city_returns_default(self):
        result = get_current_weather("Mars")
        assert "unknown" in result
        assert "20 C" in result

    def test_empty_location(self):
        result = get_current_weather("")
        assert "unknown" in result


class TestSystemStatusTool:
    def test_returns_cpu_info(self):
        result = get_system_status()
        assert "CPU usage" in result

    def test_returns_memory_info(self):
        result = get_system_status()
        assert "Memory usage" in result

    def test_returns_disk_info(self):
        result = get_system_status()
        assert "Disk usage" in result

    def test_returns_non_empty_string(self):
        result = get_system_status()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCalculateTool:
    def test_basic_arithmetic(self):
        from app.services.llm_service import calculate

        result = calculate("2 + 3 * 4")
        assert "14" in result

    def test_simple_addition(self):
        from app.services.llm_service import calculate

        result = calculate("1 + 1")
        assert "2" in result

    def test_round_function(self):
        from app.services.llm_service import calculate

        result = calculate("round(3.14159, 2)")
        assert "3.14" in result

    def test_pow_function(self):
        from app.services.llm_service import calculate

        result = calculate("pow(2, 10)")
        assert "1024" in result

    def test_invalid_expression(self):
        from app.services.llm_service import calculate

        result = calculate("1 / 0")
        assert "Calculation failed" in result

    def test_safety_no_builtins(self):
        from app.services.llm_service import calculate

        result = calculate("__import__('os').system('ls')")
        assert "Calculation failed" in result
