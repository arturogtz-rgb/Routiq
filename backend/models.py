"""Pydantic models for Routiq."""
from __future__ import annotations
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import List, Optional, Literal, Dict, Any


# ---------- Auth ----------
class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    name: str
    role: str
    tenant_id: Optional[str] = None
    status: str = "active"


# ---------- Companies (tenants) ----------
class WhatsAppNumber(BaseModel):
    id: str
    number: str
    label: str = ""
    status: str = "disconnected"


class PricingCommissions(BaseModel):
    directo: float = 0.0
    agencia: float = 0.10
    mayorista: float = 0.15
    operador: float = 0.20


class PricingConfig(BaseModel):
    margin_divisor: float = 0.76
    commissions: PricingCommissions = Field(default_factory=PricingCommissions)
    minor_age_min: int = 3
    minor_age_max: int = 11
    minor_discount: float = 0.40
    currency: str = "MXN"


class CompanyCreate(BaseModel):
    name: str
    slug: str
    contact_email: EmailStr
    contact_phone: str = ""
    address: str = ""
    admin_name: str
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)


class CompanyPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    slug: str
    logo_url: str = ""
    primary_color: str = "#185FA5"
    contact_email: str = ""
    contact_phone: str = ""
    address: str = ""
    pricing_config: PricingConfig
    whatsapp_numbers: List[WhatsAppNumber] = []
    status: str = "active"
    created_at: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    pricing_config: Optional[PricingConfig] = None


# ---------- Company integrations & payments ----------
class CompanyIntegrationsUpdate(BaseModel):
    stripe_publishable_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    stripe_enabled: Optional[bool] = None
    resend_api_key: Optional[str] = None
    resend_from_email: Optional[str] = None
    resend_from_name: Optional[str] = None
    base_currency: Optional[Literal["MXN", "USD"]] = None
    deposit_percent: Optional[float] = Field(default=None, ge=1, le=100)
    notify_email: Optional[str] = None


class QuotationPricingAdjust(BaseModel):
    discount_type: Literal["none", "fixed", "percent"] = "none"
    discount_value: float = Field(default=0.0, ge=0)


class PublicCheckoutRequest(BaseModel):
    origin_url: str
    pay_type: Literal["total", "deposit"] = "total"


# ---------- Users ----------
class InviteExecutive(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)


# ---------- Catalogs ----------
class ItineraryDay(BaseModel):
    day: int
    title: str
    description: str = ""


class PackageHotel(BaseModel):
    name: str
    category: str = ""
    prices_by_occupancy: Dict[str, float]  # sencilla, doble, triple, cuadruple
    minor_price: float = 0.0


class PackageCreate(BaseModel):
    code: str
    name: str
    nights: int
    description: str = ""
    itinerary: List[ItineraryDay] = []
    hotels: List[PackageHotel] = []
    includes: List[str] = []
    excludes: List[str] = []
    season_start: Optional[str] = None
    season_end: Optional[str] = None
    status: str = "active"


class PackageUpdate(BaseModel):
    name: Optional[str] = None
    nights: Optional[int] = None
    description: Optional[str] = None
    itinerary: Optional[List[ItineraryDay]] = None
    hotels: Optional[List[PackageHotel]] = None
    includes: Optional[List[str]] = None
    excludes: Optional[List[str]] = None
    season_start: Optional[str] = None
    season_end: Optional[str] = None
    status: Optional[str] = None


# ---------- Services (a la carte) ----------
ServiceCategory = Literal["tour", "traslado", "acceso", "extra"]


class ServiceCreate(BaseModel):
    name: str
    category: ServiceCategory = "tour"
    description: str = ""
    net_price: float = 0.0
    public_price: float = 0.0  # if 0, server auto-computes from net via margin_divisor
    per_person: bool = False
    status: str = "active"


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[ServiceCategory] = None
    description: Optional[str] = None
    net_price: Optional[float] = None
    public_price: Optional[float] = None
    per_person: Optional[bool] = None
    status: Optional[str] = None


class SelectedService(BaseModel):
    service_id: str
    qty: int = Field(default=1, ge=1)


# ---------- Clients ----------
class ClientCreate(BaseModel):
    name: str
    phone: str = ""
    email: str = ""
    channel: Literal["directo", "agencia", "mayorista", "operador"] = "directo"
    notes: str = ""


# ---------- Quotations ----------
OCCUPANCY_COUNT = {"sencilla": 1, "doble": 2, "triple": 3, "cuadruple": 4}


class QuotationRoom(BaseModel):
    ocupacion: Literal["sencilla", "doble", "triple", "cuadruple"] = "doble"
    count: int = Field(default=1, ge=1, le=20)  # cuántas habitaciones de este tipo


class QuotationPax(BaseModel):
    # Legacy fields (back-compat for old quotations)
    adultos: int = 0
    menores: int = 0
    ocupacion: Literal["sencilla", "doble", "triple", "cuadruple"] = "doble"
    # New multi-room structure
    rooms: List[QuotationRoom] = []

    def total_adults(self) -> int:
        if self.rooms:
            return sum(OCCUPANCY_COUNT[r.ocupacion] * r.count for r in self.rooms)
        return self.adultos


class QuotationDates(BaseModel):
    start: str
    end: str


class QuotationCreate(BaseModel):
    client_id: str
    package_id: str
    hotel_name: str
    dates: QuotationDates
    pax: QuotationPax
    services: List[SelectedService] = []
    notes: str = ""
    assigned_to: Optional[str] = None


class QuotationStateUpdate(BaseModel):
    state: Literal["nueva_consulta", "cotizando", "enviada", "negociacion", "ganada", "perdida"]


class QuotationUpdate(BaseModel):
    dates: Optional[QuotationDates] = None
    pax: Optional[QuotationPax] = None
    hotel_name: Optional[str] = None
    services: Optional[List[SelectedService]] = None
    notes: Optional[str] = None
    assigned_to: Optional[str] = None
