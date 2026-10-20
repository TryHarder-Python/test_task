from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from cache_service.repositories.interfaces import UnitOfWork
from cache_service.repositories.postgres import PostgresUnitOfWork
from cache_service.schemas import PayloadCreate, PayloadCreated, PayloadRead
from cache_service.service import PayloadService
from cache_service.transformer import Transformer

router = APIRouter()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_transformer(request: Request) -> Transformer:
    return request.app.state.transformer


def get_unit_of_work(session: Annotated[AsyncSession, Depends(get_session)]) -> UnitOfWork:
    return PostgresUnitOfWork(session)


def get_service(
    uow: Annotated[UnitOfWork, Depends(get_unit_of_work)],
    transformer: Annotated[Transformer, Depends(get_transformer)],
) -> PayloadService:
    return PayloadService(uow, transformer)


ServiceDep = Annotated[PayloadService, Depends(get_service)]


@router.post(
    "/payload",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"model": PayloadCreated, "description": "Already exists"}},
)
async def create_payload(
    body: PayloadCreate, response: Response, service: ServiceDep
) -> PayloadCreated:
    payload_id, created = await service.create(body)
    if not created:
        response.status_code = status.HTTP_200_OK
        return PayloadCreated(id=payload_id, message="Payload already exists")

    return PayloadCreated(id=payload_id, message="Payload created")


@router.get("/payload/{payload_id}", responses={status.HTTP_404_NOT_FOUND: {}})
async def read_payload(payload_id: UUID, service: ServiceDep) -> PayloadRead:
    output = await service.get_output(payload_id)
    if output is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Payload not found")
    return PayloadRead(output=output)


@router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}
