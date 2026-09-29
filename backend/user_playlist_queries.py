"""Owner-scoped database queries shared by playlist use cases."""

from sqlalchemy.orm import Session, selectinload

import models


def get_owned_playlist(db: Session, owner_user_id: int, playlist_id: int):
    return (
        db.query(models.UserPlaylist)
        .options(selectinload(models.UserPlaylist.items))
        .filter(
            models.UserPlaylist.id == playlist_id,
            models.UserPlaylist.owner_user_id == owner_user_id,
        )
        .one_or_none()
    )
