"""Minimal config flow: a single entry that owns the SmartIR devices.

SmartIR entities are still defined in YAML. This entry exists only so the
devices can be registered under a config entry and show up in the UI.
"""

from homeassistant.config_entries import ConfigFlow

DOMAIN = "smartir"


class SmartIRConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="SmartIR", data={})
        return self.async_show_form(step_id="user")
