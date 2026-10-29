"""Discover only the targeted model; configuration never sends motor commands."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
    from homeassistant.config_entries import ConfigEntry, ConfigFlowResult

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback

DOMAIN = "urevo_local"


def finite_speed(value: Any) -> float:
    if isinstance(value, bool):
        raise vol.Invalid("Speed must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise vol.Invalid("Speed must be finite")
    return value


def options_schema(options: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                "allow_control", default=options.get("allow_control", False)
            ): bool,
            vol.Optional("max_speed", default=options.get("max_speed", 1.6)): vol.All(
                vol.Coerce(finite_speed), vol.Range(min=0.5, max=6.4)
            ),
        }
    )


class UrevoConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        devices = {
            info.address: f"{info.name} ({info.address})"
            for info in bluetooth.async_discovered_service_info(
                self.hass, connectable=True
            )
            if info.name == "URTM041"
        }
        if user_input is not None:
            address = user_input["address"]
            if address not in devices:
                return self.async_abort(reason="no_devices_found")
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="UREVO walking pad", data={"address": address}
            )
        if not devices:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("address"): vol.In(devices)}),
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        if discovery_info.name != "URTM041":
            return self.async_abort(reason="not_supported")
        self._address = discovery_info.address
        await self.async_set_unique_id(self._address)
        self._abort_if_unique_id_configured()
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="UREVO walking pad", data={"address": self._address}
            )
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"address": self._address},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> UrevoOptionsFlow:
        return UrevoOptionsFlow()


class UrevoOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            try:
                validated = options_schema(self.config_entry.options)(user_input)
            except vol.Invalid:
                return self.async_show_form(
                    step_id="init",
                    data_schema=options_schema(self.config_entry.options),
                    errors={"base": "invalid_options"},
                )
            return self.async_create_entry(title="", data=validated)
        return self.async_show_form(
            step_id="init", data_schema=options_schema(self.config_entry.options)
        )
