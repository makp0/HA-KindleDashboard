"""Kindle Dashboard — supports multiple dashboard instances."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DASHBOARD_NAME,
    CONF_FONT,
    CONF_HIDE_ENTITY_NAMES,
    CONF_INLINE_UNITS,
    CONF_LOCATION_NAME,
    CONF_SECTIONS,
    CONFIG_VERSION,
    DEFAULT_FONT,
    DEFAULT_HARD_REFRESH,
    DEFAULT_REFRESH_INTERVAL,
    DEFAULT_HIDE_ENTITY_NAMES,
    DEFAULT_INLINE_UNITS,
    DEFAULT_LABEL_BOLD,
    DEFAULT_LABEL_FONT_SIZE,
    DEFAULT_LABEL_ITALIC,
    DEFAULT_LABEL_UNDERLINE,
    DEFAULT_LOCATION_NAME,
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_SCALE,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_SECTIONS,
    DEFAULT_SHOW_BATTERY,
    DEFAULT_SHOW_CLOCK,
    DEFAULT_SUB_BOLD,
    DEFAULT_SUB_FONT_SIZE,
    DEFAULT_SUB_ITALIC,
    DEFAULT_SUB_UNDERLINE,
    DEFAULT_THEME,
    DEFAULT_VALUE_BOLD,
    DEFAULT_VALUE_FONT_SIZE,
    DEFAULT_VALUE_ITALIC,
    DEFAULT_VALUE_UNDERLINE,
    DOMAIN,
)
from . import websocket_api

_LOGGER = logging.getLogger(__name__)

PANEL_ICON  = "mdi:tablet"
PANEL_TITLE = "Kindle Dashboard"
STATIC_URL  = f"/{DOMAIN}_files"

_DEVICE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _script_json(value: Any) -> str:
    """Serialize JSON without letting text terminate the script element."""
    return json.dumps(value).replace("<", "\\u003c")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry
    hass.data[DOMAIN].setdefault("_reload_counters", {})
    hass.data[DOMAIN]["_reload_counters"].setdefault(entry.entry_id, 0)
    hass.data[DOMAIN].setdefault("_heartbeats", {})
    hass.data[DOMAIN]["_heartbeats"].setdefault(entry.entry_id, {})

    # Register static files and panel only once (first entry)
    if not hass.data[DOMAIN].get("_panel_registered"):
        frontend_path = os.path.join(os.path.dirname(__file__), "frontend")
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, frontend_path, cache_headers=False)]
        )
        try:
            from homeassistant.components import panel_custom
            await panel_custom.async_register_panel(
                hass,
                webcomponent_name="kindle-dashboard-panel",
                frontend_url_path=DOMAIN,
                sidebar_title=PANEL_TITLE,
                sidebar_icon=PANEL_ICON,
                module_url=f"{STATIC_URL}/panel.js",
                embed_iframe=False,
                require_admin=True,
            )
            hass.data[DOMAIN]["_panel_registered"] = True
        except Exception:
            _LOGGER.exception("Failed to register Kindle Dashboard panel")

        # Register HTTP views once
        hass.http.register_view(KindleView(hass))
        hass.http.register_view(KindleReloadView(hass))

    websocket_api.async_setup(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data[DOMAIN].pop(entry.entry_id, None)
    hass.data[DOMAIN].get("_reload_counters", {}).pop(entry.entry_id, None)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries — preserves all user data."""
    _LOGGER.debug("Migrating Kindle Dashboard from v%s to v%s",
                  entry.version, CONFIG_VERSION)
    data    = {**entry.data}
    options = {**entry.options}

    if entry.version < 2:
        for store in (data, options):
            store.setdefault(CONF_FONT,             DEFAULT_FONT)
            store.setdefault(CONF_INLINE_UNITS,     DEFAULT_INLINE_UNITS)
            store.setdefault(CONF_HIDE_ENTITY_NAMES,DEFAULT_HIDE_ENTITY_NAMES)
            if CONF_SECTIONS not in store:
                store[CONF_SECTIONS] = DEFAULT_SECTIONS

    if entry.version < 3:
        # Add dashboard_name from entry title (or default)
        for store in (data, options):
            store.setdefault(CONF_DASHBOARD_NAME, entry.title or "Kindle Dashboard")

    hass.config_entries.async_update_entry(
        entry, data=data, options=options, version=CONFIG_VERSION
    )
    return True


def _merged_config(entry: ConfigEntry) -> dict:
    """Merge entry data + options over defaults. New keys always have a value."""
    base = {
        CONF_LOCATION_NAME:     DEFAULT_LOCATION_NAME,
        CONF_SECTIONS:          DEFAULT_SECTIONS,
        CONF_FONT:              DEFAULT_FONT,
        CONF_INLINE_UNITS:      DEFAULT_INLINE_UNITS,
        CONF_HIDE_ENTITY_NAMES: DEFAULT_HIDE_ENTITY_NAMES,
        CONF_DASHBOARD_NAME:    entry.title or "Kindle Dashboard",
        "page_width":           DEFAULT_PAGE_WIDTH,
        "page_height":          DEFAULT_PAGE_HEIGHT,
        "page_scale":           DEFAULT_PAGE_SCALE,
        "hard_refresh":         DEFAULT_HARD_REFRESH,
        "refresh_interval":     DEFAULT_REFRESH_INTERVAL,
        "show_clock":           DEFAULT_SHOW_CLOCK,
        "show_battery":         DEFAULT_SHOW_BATTERY,
        "theme":                DEFAULT_THEME,
        "label_font_size":      DEFAULT_LABEL_FONT_SIZE,
        "label_bold":           DEFAULT_LABEL_BOLD,
        "label_italic":         DEFAULT_LABEL_ITALIC,
        "label_underline":      DEFAULT_LABEL_UNDERLINE,
        "sub_font_size":        DEFAULT_SUB_FONT_SIZE,
        "sub_bold":             DEFAULT_SUB_BOLD,
        "sub_italic":           DEFAULT_SUB_ITALIC,
        "sub_underline":        DEFAULT_SUB_UNDERLINE,
        "value_font_size":      DEFAULT_VALUE_FONT_SIZE,
        "value_bold":           DEFAULT_VALUE_BOLD,
        "value_italic":         DEFAULT_VALUE_ITALIC,
        "value_underline":      DEFAULT_VALUE_UNDERLINE,
        # User-set fields — not in DEFAULT_* constants; fall back to empty
        "kindle_token":         "",
        "devices":              [],
        "dashboard_name":       entry.title or "Kindle Dashboard",
    }
    base.update(entry.data)
    base.update(entry.options)
    # Always expose entry_id so the panel can use it
    base["entry_id"] = entry.entry_id
    return base


def bump_reload_counter(hass: HomeAssistant, entry_id: str) -> int:
    counters = hass.data.get(DOMAIN, {}).get("_reload_counters", {})
    counters[entry_id] = counters.get(entry_id, 0) + 1
    return counters[entry_id]


class KindleView(HomeAssistantView):
    """Serve a dashboard at /api/kindle_dashboard/kindle/{entry_id}?token=..."""

    url  = "/api/kindle_dashboard/kindle/{entry_id}"
    name = "api:kindle_dashboard:kindle"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: Any, entry_id: str) -> Any:
        from aiohttp.web import Response

        token = request.rel_url.query.get("token", "").strip()
        if not token:
            return Response(
                text=_NO_TOKEN_PAGE, content_type="text/html", charset="utf-8",
                headers=_DEVICE_HEADERS,
            )
        if self.hass.auth.async_validate_access_token(token) is None:
            return Response(text="Invalid credential.", status=401, headers=_DEVICE_HEADERS)

        # Find the entry
        entry = None
        for e in self.hass.config_entries.async_entries(DOMAIN):
            if e.entry_id == entry_id:
                entry = e
                break

        if entry is None:
            return Response(text="Dashboard not found.", status=404)

        cfg              = _merged_config(entry)
        location         = cfg.get(CONF_LOCATION_NAME,    DEFAULT_LOCATION_NAME)
        sections         = cfg.get(CONF_SECTIONS,         DEFAULT_SECTIONS)
        font             = cfg.get(CONF_FONT,             DEFAULT_FONT)
        inline_units     = cfg.get(CONF_INLINE_UNITS,     DEFAULT_INLINE_UNITS)
        page_width       = int(cfg.get("page_width",      DEFAULT_PAGE_WIDTH))
        page_height      = int(cfg.get("page_height",     DEFAULT_PAGE_HEIGHT))
        page_scale       = float(cfg.get("page_scale",    DEFAULT_PAGE_SCALE))
        hard_refresh     = cfg.get("hard_refresh",        DEFAULT_HARD_REFRESH)
        refresh_interval = int(cfg.get("refresh_interval", DEFAULT_REFRESH_INTERVAL))
        show_clock       = cfg.get("show_clock",          DEFAULT_SHOW_CLOCK)
        show_battery     = cfg.get("show_battery",        DEFAULT_SHOW_BATTERY)
        theme            = cfg.get("theme",               DEFAULT_THEME)
        label_font_size  = cfg.get("label_font_size",     DEFAULT_LABEL_FONT_SIZE)
        label_bold       = cfg.get("label_bold",          DEFAULT_LABEL_BOLD)
        label_italic     = cfg.get("label_italic",        DEFAULT_LABEL_ITALIC)
        label_underline  = cfg.get("label_underline",     DEFAULT_LABEL_UNDERLINE)
        sub_font_size    = cfg.get("sub_font_size",       DEFAULT_SUB_FONT_SIZE)
        sub_bold         = cfg.get("sub_bold",            DEFAULT_SUB_BOLD)
        sub_italic       = cfg.get("sub_italic",          DEFAULT_SUB_ITALIC)
        sub_underline    = cfg.get("sub_underline",       DEFAULT_SUB_UNDERLINE)
        value_font_size  = cfg.get("value_font_size",     DEFAULT_VALUE_FONT_SIZE)
        value_bold       = cfg.get("value_bold",          DEFAULT_VALUE_BOLD)
        value_italic     = cfg.get("value_italic",        DEFAULT_VALUE_ITALIC)
        value_underline  = cfg.get("value_underline",     DEFAULT_VALUE_UNDERLINE)

        template_path = os.path.join(os.path.dirname(__file__), "frontend", "kindle.html")
        with open(template_path, "r", encoding="utf-8") as f:
            html = f.read()

        injected = (
            f"const PAGE_WIDTH       = {_script_json(page_width)};\n"
            f"const PAGE_HEIGHT      = {_script_json(page_height)};\n"
            f"const PAGE_SCALE       = {_script_json(page_scale)};\n"
            f"const HA_URL           = window.location.origin;\n"
            f"const HA_TOKEN         = {_script_json(token)};\n"
            f"const ENTRY_ID         = {_script_json(entry_id)};\n"
            f"const LOCATION         = {_script_json(location)};\n"
            f"const SECTIONS         = {_script_json(sections)};\n"
            f"const BODY_FONT        = {_script_json(font)};\n"
            f"const INLINE_UNITS     = {_script_json(inline_units)};\n"
            f"const HARD_REFRESH       = {_script_json(hard_refresh)};\n"
            f"const REFRESH_INTERVAL  = {_script_json(refresh_interval)};\n"
            f"const SHOW_CLOCK       = {_script_json(show_clock)};\n"
            f"const SHOW_BATTERY     = {_script_json(show_battery)};\n"
            f"const THEME            = {_script_json(theme)};\n"
            f"const LABEL_FONT_SIZE  = {_script_json(label_font_size)};\n"
            f"const LABEL_BOLD       = {_script_json(label_bold)};\n"
            f"const LABEL_ITALIC     = {_script_json(label_italic)};\n"
            f"const LABEL_UNDERLINE  = {_script_json(label_underline)};\n"
            f"const SUB_FONT_SIZE    = {_script_json(sub_font_size)};\n"
            f"const SUB_BOLD         = {_script_json(sub_bold)};\n"
            f"const SUB_ITALIC       = {_script_json(sub_italic)};\n"
            f"const SUB_UNDERLINE    = {_script_json(sub_underline)};\n"
            f"const VALUE_FONT_SIZE  = {_script_json(value_font_size)};\n"
            f"const VALUE_BOLD       = {_script_json(value_bold)};\n"
            f"const VALUE_ITALIC     = {_script_json(value_italic)};\n"
            f"const VALUE_UNDERLINE  = {_script_json(value_underline)};\n"
        )
        html = html.replace("/* __INJECTED_CONFIG__ */", injected)
        html = html.replace(
            "/* __VIEWPORT_WIDTH__ */",
            f"width={page_width}, initial-scale=1.0, maximum-scale=1.0"
        )
        return Response(text=html, content_type="text/html", charset="utf-8", headers=_DEVICE_HEADERS)


class KindleReloadView(HomeAssistantView):
    """Serve the reload counter at /api/kindle_dashboard/reload/{entry_id}?token=..."""

    url  = "/api/kindle_dashboard/reload/{entry_id}"
    name = "api:kindle_dashboard:reload"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: Any, entry_id: str) -> Any:
        from aiohttp.web import Response
        import time
        token = request.rel_url.query.get("token", "").strip()
        if not token or self.hass.auth.async_validate_access_token(token) is None:
            return Response(text="Valid credential required.", status=401, headers=_DEVICE_HEADERS)
        if self.hass.data.get(DOMAIN, {}).get(entry_id) is None:
            return Response(text="Dashboard not found.", status=404, headers=_DEVICE_HEADERS)
        # Record heartbeat — use last 8 chars of token as client key
        client_key = token[-8:] if len(token) >= 8 else token
        beats = self.hass.data.get(DOMAIN, {}).get("_heartbeats", {})
        beats.setdefault(entry_id, {})[client_key] = time.time()
        # Prune clients not seen in 30 seconds
        now = time.time()
        beats[entry_id] = {
            k: v for k, v in beats.get(entry_id, {}).items()
            if now - v < 30
        }
        counter = self.hass.data.get(DOMAIN, {}).get(
            "_reload_counters", {}
        ).get(entry_id, 0)
        return Response(
            text=str(counter),
            content_type="text/plain",
            headers=_DEVICE_HEADERS,
        )


_NO_TOKEN_PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=536,initial-scale=1">
<title>Kindle Dashboard — Setup</title>
<style>
  body{font-family:'Courier New',monospace;background:#fff;color:#000;
       padding:24px;line-height:1.6}
  h1{font-size:18px;border-bottom:3px solid #000;padding-bottom:8px;margin-bottom:16px}
  ol{padding-left:20px} li{margin-bottom:10px}
  code{background:#eee;padding:2px 6px;font-size:13px;word-break:break-all}
  .box{border:2px solid #000;padding:12px;margin-top:16px;font-size:13px}
</style></head><body>
<h1>Kindle Dashboard — token required</h1>
<p>A long-lived access token must be included in the URL.</p>
<ol>
  <li>In Home Assistant, click your profile (bottom-left avatar).</li>
  <li>Scroll to <strong>Long-Lived Access Tokens</strong> and create one named <em>Kindle</em>.</li>
  <li>The Kindle Dashboard panel in HA shows the correct pre-filled URL for each dashboard.</li>
</ol>
<div class="box">Each dashboard has its own URL containing its unique ID.</div>
</body></html>"""
