"""
AIQE FastAPI — Plugin Endpoints.

GET  /plugins              — list loaded plugins
GET  /plugins/{name}       — get plugin details
POST /plugins/validate     — validate a plugin manifest
GET  /plugins/capabilities — list all capabilities
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status

from aiqe.api.dependencies import AuthDep, PluginRegistryDep
from aiqe.api.schemas import (
    CapabilitySchema,
    PluginInfoResponse,
    ValidateManifestRequest,
    ValidateManifestResponse,
)

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get(
    "",
    summary="List all loaded plugins",
    description="Returns all plugins currently registered with AIQE.",
)
async def list_plugins(
    registry: PluginRegistryDep,
    auth: AuthDep,
    plugin_type: Optional[str] = Query(
        default=None,
        description="Filter by plugin type.",
    ),
) -> dict[str, Any]:
    """List all loaded plugins."""
    if plugin_type:
        plugins = registry.get_by_type(plugin_type)
    else:
        plugins = registry.all_plugins()

    return {
        "plugins": [
            {
                "name": p.manifest.name,
                "version": p.manifest.version,
                "type": p.manifest.plugin_type,
                "author": p.manifest.author,
                "is_healthy": p.is_healthy,
                "capability_count": len(p.manifest.required_capabilities),
                "has_restricted": p.manifest.has_restricted_capabilities,
            }
            for p in plugins
        ],
        "total": len(plugins),
    }


@router.get(
    "/capabilities",
    summary="List all plugin capabilities",
    description=(
        "Returns all capabilities plugins can declare in their manifests."
    ),
)
async def list_capabilities(
    auth: AuthDep,
    group: Optional[str] = Query(
        default=None,
        description="Filter by capability group.",
    ),
    restricted_only: bool = Query(
        default=False,
        description="Return only restricted capabilities.",
    ),
) -> dict[str, Any]:
    """List all available plugin capabilities."""
    from aiqe.plugins.capabilities import Capabilities, CapabilityGroup

    caps = Capabilities.all()

    if group:
        try:
            cap_group = CapabilityGroup(group.lower())
            caps = [c for c in caps if c.group == cap_group]
        except ValueError:
            valid = [g.value for g in CapabilityGroup]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown group '{group}'. Valid: {valid}",
            )

    if restricted_only:
        caps = [c for c in caps if c.is_restricted]

    return {
        "capabilities": [
            CapabilitySchema(
                id=c.id,
                group=c.group.value,
                display_name=c.display_name,
                description=c.description,
                is_restricted=c.is_restricted,
                risk_level=c.risk_level,
            ).model_dump()
            for c in sorted(caps, key=lambda c: (c.group.value, c.id))
        ],
        "total": len(caps),
    }


@router.post(
    "/validate",
    response_model=ValidateManifestResponse,
    summary="Validate a plugin manifest",
    description=(
        "Validates a plugin manifest dict without loading the plugin. "
        "Returns validation errors and warnings."
    ),
)
async def validate_manifest(
    request: ValidateManifestRequest,
    auth: AuthDep,
) -> ValidateManifestResponse:
    """Validate a plugin manifest."""
    from aiqe.plugins.manifest import ManifestLoader
    from aiqe.shared.exceptions import PluginManifestError

    loader = ManifestLoader()
    errors = []
    warnings = []

    try:
        manifest = loader.load_from_dict(request.manifest)

        if manifest.has_restricted_capabilities:
            warnings.append(
                f"Plugin requests {len([c for c in manifest.required_capabilities if c.is_restricted])} "
                f"restricted capability/capabilities. Users will be prompted for approval."
            )

        if manifest.max_risk_level >= 4:
            warnings.append(
                "Plugin requests at least one critical-risk capability. "
                "Ensure this plugin is from a trusted source."
            )

        return ValidateManifestResponse(
            is_valid=True,
            plugin_name=manifest.name,
            plugin_type=manifest.plugin_type,
            capability_count=len(manifest.required_capabilities),
            has_restricted=manifest.has_restricted_capabilities,
            max_risk_level=manifest.max_risk_level,
            errors=errors,
            warnings=warnings,
        )

    except PluginManifestError as e:
        errors.append(str(e))
        return ValidateManifestResponse(
            is_valid=False,
            errors=errors,
            warnings=warnings,
        )


@router.get(
    "/{plugin_name}",
    response_model=PluginInfoResponse,
    summary="Get plugin details",
    description="Returns detailed information about a specific loaded plugin.",
)
async def get_plugin(
    plugin_name: str,
    registry: PluginRegistryDep,
    auth: AuthDep,
) -> PluginInfoResponse:
    """Get details for a specific plugin."""
    from aiqe.shared.exceptions import PluginLoadError

    try:
        loaded = registry.get(plugin_name)
    except PluginLoadError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "plugin_not_found",
                "plugin_name": plugin_name,
            },
        )

    manifest = loaded.manifest
    return PluginInfoResponse(
        name=manifest.name,
        version=manifest.version,
        plugin_type=manifest.plugin_type,
        author=manifest.author,
        description=manifest.description,
        is_healthy=loaded.is_healthy,
        required_capabilities=[
            CapabilitySchema(
                id=c.id,
                group=c.group.value,
                display_name=c.display_name,
                description=c.description,
                is_restricted=c.is_restricted,
                risk_level=c.risk_level,
            )
            for c in manifest.required_capabilities
        ],
        has_restricted_capabilities=manifest.has_restricted_capabilities,
        max_risk_level=manifest.max_risk_level,
    )
