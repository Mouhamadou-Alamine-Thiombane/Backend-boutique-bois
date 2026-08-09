from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.database import get_pool
from app.schemas import NotificationOut

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationOut])
async def lister_notifications(non_lues_seulement: bool = False, current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    query = "SELECT * FROM notifications WHERE utilisateur_id = $1"
    if non_lues_seulement:
        query += " AND est_lu = FALSE"
    query += " ORDER BY date_creation DESC LIMIT 100"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, current_user["id"])
    return [NotificationOut(**dict(r)) for r in rows]


@router.patch("/{notification_id}/lu", response_model=NotificationOut)
async def marquer_lu(notification_id: UUID, current_user: dict = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE notifications SET est_lu = TRUE, date_lecture = now()
            WHERE id = $1 AND utilisateur_id = $2
            RETURNING *
            """,
            notification_id,
            current_user["id"],
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    return NotificationOut(**dict(row))
