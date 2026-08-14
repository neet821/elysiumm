from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

import book_service
import models
import schemas
from database import get_db
from dependencies import get_current_user


router = APIRouter(tags=["books"])


def administrator(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, book_service.BookNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, book_service.BookDuplicate):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, book_service.BookRevisionConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, book_service.BookListMembershipError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/api/books", response_model=schemas.BookCatalogPublicResponse)
def get_public_books(db: Session = Depends(get_db)):
    return book_service.public_catalog(db)


@router.get("/api/admin/books", response_model=schemas.BookCatalogAdminResponse)
def get_admin_books(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(administrator),
):
    return book_service.admin_catalog(db)


@router.post(
    "/api/admin/books",
    response_model=schemas.BookAdminView,
    status_code=status.HTTP_201_CREATED,
)
def create_book(
    payload: schemas.BookCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(administrator),
):
    try:
        return book_service.create_book(db, payload, actor_id=current_user.id)
    except Exception as exc:
        db.rollback()
        _raise_service_error(exc)


@router.put("/api/admin/books/{book_id}", response_model=schemas.BookAdminView)
def update_book(
    book_id: int,
    payload: schemas.BookUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(administrator),
):
    try:
        return book_service.update_book(
            db,
            book_id,
            payload,
            actor_id=current_user.id,
        )
    except Exception as exc:
        db.rollback()
        _raise_service_error(exc)


@router.delete("/api/admin/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    book_id: int,
    revision: int = Query(ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(administrator),
):
    try:
        book_service.delete_book(
            db,
            book_id,
            revision=revision,
            actor_id=current_user.id,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post(
    "/api/admin/book-lists",
    response_model=schemas.BookListAdminView,
    status_code=status.HTTP_201_CREATED,
)
def create_book_list(
    payload: schemas.BookListCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(administrator),
):
    try:
        return book_service.create_book_list(db, payload, actor_id=current_user.id)
    except Exception as exc:
        db.rollback()
        _raise_service_error(exc)


@router.put(
    "/api/admin/book-lists/{list_id}",
    response_model=schemas.BookListAdminView,
)
def update_book_list(
    list_id: int,
    payload: schemas.BookListUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(administrator),
):
    try:
        return book_service.update_book_list(
            db,
            list_id,
            payload,
            actor_id=current_user.id,
        )
    except Exception as exc:
        db.rollback()
        _raise_service_error(exc)


@router.put(
    "/api/admin/book-lists/{list_id}/items",
    response_model=schemas.BookListAdminView,
)
def replace_book_list_items(
    list_id: int,
    payload: schemas.BookListItemsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(administrator),
):
    try:
        return book_service.replace_book_list_items(
            db,
            list_id,
            payload,
            actor_id=current_user.id,
        )
    except Exception as exc:
        db.rollback()
        _raise_service_error(exc)


@router.delete(
    "/api/admin/book-lists/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_book_list(
    list_id: int,
    revision: int = Query(ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(administrator),
):
    try:
        book_service.delete_book_list(
            db,
            list_id,
            revision=revision,
            actor_id=current_user.id,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        db.rollback()
        _raise_service_error(exc)
