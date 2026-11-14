"""Register a UI device for a YAML-defined SmartIR entity."""

import logging

from homeassistant.helpers import device_registry as dr, entity_registry as er

DOMAIN = "smartir"
_LOGGER = logging.getLogger(__name__)


def link_device(entity):
    """Create (or update) a device for the entity and link the entity to it.

    Needs the SmartIR config entry (added once from the UI). Without it, or on
    any failure, the entity keeps working as before, just without a device.
    """
    try:
        hass = entity.hass
        unique_id = entity.unique_id
        entity_id = entity.entity_id
        if not unique_id or not entity_id:
            return
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            _LOGGER.debug("No SmartIR config entry; skipping device registration")
            return
        model = getattr(entity, "_supported_models", None)
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entries[0].entry_id,
            identifiers={(DOMAIN, str(unique_id))},
            name=getattr(entity, "_name", None) or str(unique_id),
            manufacturer=getattr(entity, "_manufacturer", None),
            model=", ".join(model) if isinstance(model, (list, tuple)) else model,
            model_id=str(getattr(entity, "_device_code", "")) or None,
        )
        ent_reg = er.async_get(hass)
        reg_entry = ent_reg.async_get(entity_id)
        if reg_entry is not None and reg_entry.device_id != device.id:
            ent_reg.async_update_entity(entity_id, device_id=device.id)
    except Exception:  # never break the entity because of device registration
        _LOGGER.exception("SmartIR device registration failed for %s", entity)
