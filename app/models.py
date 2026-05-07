from dataclasses import dataclass


@dataclass
class User:
    id: int
    tg_id: int
    full_name: str
    role: str
    default_cabinet_id: int | None


@dataclass
class Cabinet:
    id: int
    name: str


@dataclass
class CatalogItem:
    id: int
    name: str
    unit: str
    supplier: str | None
    default_qty: float
    archived_at: str | None


@dataclass
class OrderCycle:
    id: int
    status: str
    opened_at: str
    opened_by: int | None
    closed_at: str | None
    closed_by: int | None


@dataclass
class OrderRequest:
    id: int
    cycle_id: int
    user_id: int
    cabinet_id: int
    catalog_item_id: int | None
    free_form_name: str | None
    qty: float
    unit: str
    comment: str | None
    doctor_name: str | None
    status: str
    created_at: str
    updated_at: str

    @property
    def display_name(self) -> str:
        return self.free_form_name or "(з каталогу)"
