from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from music_provider_runtime import (
    CATALOG_PROVIDERS,
    music_provider_registry,
    provider_configuration_status,
)


router = APIRouter()


def _require_music_admin(user):
    if user.role != "admin":
        raise HTTPException(403, "只有管理员可以管理共享曲库账号")


@router.get("/providers/status")
async def music_provider_status(user=Depends(get_current_user)):
    _require_music_admin(user)
    return await provider_configuration_status(music_provider_registry)


@router.post("/providers/{provider}/login/start")
async def start_music_provider_login(provider: str, user=Depends(get_current_user)):
    _require_music_admin(user)
    if provider not in CATALOG_PROVIDERS:
        raise HTTPException(404, "不支持的曲库来源")
    raise HTTPException(501, "共享曲库凭据由服务器 root 配置文件管理，暂不支持网页扫码登录")


@router.get("/providers/{provider}/login/{session_id}/image")
async def music_provider_login_image(provider: str, session_id: str, user=Depends(get_current_user)):
    _require_music_admin(user)
    if provider not in CATALOG_PROVIDERS or not session_id or len(session_id) > 100:
        raise HTTPException(404, "登录任务不存在")
    raise HTTPException(501, "共享曲库凭据由服务器 root 配置文件管理，暂不支持网页扫码登录")


@router.get("/providers/{provider}/login/{session_id}")
async def music_provider_login_status(provider: str, session_id: str, user=Depends(get_current_user)):
    _require_music_admin(user)
    if provider not in CATALOG_PROVIDERS or not session_id or len(session_id) > 100:
        raise HTTPException(404, "登录任务不存在")
    raise HTTPException(501, "共享曲库凭据由服务器 root 配置文件管理，暂不支持网页扫码登录")


@router.delete("/providers/{provider}/credential")
async def delete_music_provider_credential(provider: str, user=Depends(get_current_user)):
    _require_music_admin(user)
    if provider not in CATALOG_PROVIDERS:
        raise HTTPException(404, "不支持的曲库来源")
    raise HTTPException(501, "共享曲库凭据由服务器 root 配置文件管理，请通过运维流程轮换")


@router.get("/providers/capabilities")
async def music_provider_capabilities(user=Depends(get_current_user)):
    configured = await provider_configuration_status(music_provider_registry)
    configured_providers = configured.get("providers") or {}
    netease_ready = bool((configured_providers.get("netease") or {}).get("configured"))
    qq_ready = bool((configured_providers.get("qq") or {}).get("configured"))
    audius_ready = music_provider_registry.get("audius") is not None
    return {
        "providers": [
            {
                "provider": "netease",
                "label": "网易云",
                "searchable": True,
                "playable": netease_ready,
                "reason": None if netease_ready else "歌曲播放地址会按曲目实时验证",
            },
            {
                "provider": "qq",
                "label": "QQ 音乐",
                "searchable": True,
                "playable": qq_ready,
                "reason": None if qq_ready else "服务器尚未配置 QQ 音乐凭据",
            },
            {
                "provider": "audius",
                "label": "Audius",
                "searchable": True,
                "playable": audius_ready,
                "reason": None if audius_ready else "Audius 播放适配器尚未配置",
            },
        ],
    }
