"""Pytest conftest."""
import sys
import os
from unittest.mock import MagicMock

# Add custom_components to path so relative imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components"))

# Mock homeassistant modules
class MockModule:
    pass

sys.modules["homeassistant"] = MockModule()
sys.modules["homeassistant.core"] = MockModule()
sys.modules["homeassistant.core"].HomeAssistant = MagicMock
sys.modules["homeassistant.config_entries"] = MockModule()
sys.modules["homeassistant.config_entries"].ConfigEntry = MagicMock
sys.modules["homeassistant.config_entries"].ConfigFlow = MagicMock
sys.modules["homeassistant.config_entries"].OptionsFlow = MagicMock
sys.modules["homeassistant.config_entries"].SOURCE_REAUTH = "reauth"
sys.modules["homeassistant.helpers"] = MockModule()
sys.modules["homeassistant.helpers.storage"] = MagicMock()
sys.modules["homeassistant.helpers.update_coordinator"] = MagicMock()
sys.modules["homeassistant.helpers.aiohttp_client"] = MagicMock()
sys.modules["homeassistant.helpers.selector"] = MockModule()
sys.modules["homeassistant.const"] = MockModule()
sys.modules["homeassistant.exceptions"] = MagicMock()
sys.modules["homeassistant.components"] = MagicMock()
sys.modules["homeassistant.data_entry_flow"] = MockModule()

import socket
socket.gaierror = OSError
