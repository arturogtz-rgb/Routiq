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
    # Plan & per-company controls (managed by Master). Permissive defaults so
    # pre-existing companies keep full functionality until a plan is assigned.
    plan: str = "pro"
    exec_limit: int = 0  # 0 = ilimitado
    ai_enabled: bool = True
    white_label: bool = False
    routiq_logo_fallback: bool = True
    stripe_allowed: bool = True
    transfer_allowed: bool = True
    email_provider: str = "resend"
    cancellation_policy: str = ""  # rich-text HTML, inyectado en PDFs y enlaces públicos
    created_at: Optional[str] = None


class PolicyUpdate(BaseModel):
    cancellation_policy: str = ""


class CompanyPlanUpdate(BaseModel):
    plan: Optional[Literal["starter", "pro", "enterprise"]] = None
    exec_limit: Optional[int] = Field(default=None, ge=0)
    ai_enabled: Optional[bool] = None
    white_label: Optional[bool] = None
    routiq_logo_fallback: Optional[bool] = None
    stripe_allowed: Optional[bool] = None
    transfer_allowed: Optional[bool] = None


# ---------- Tenant self-service signup (public funnel) ----------
class SignupRequest(BaseModel):
    company_name: str = Field(min_length=2)
    admin_name: str = Field(min_length=2)
    admin_email: EmailStr
    admin_phone: str = ""
    plan: Literal["starter", "pro", "enterprise"] = "pro"
    admin_password: str = Field(min_length=8)
    turnstile_token: Optional[str] = None
    website: str = ""  # honeypot — must stay empty for real humans


class SignupApprove(BaseModel):
    slug: Optional[str] = None  # Master can adjust the auto-generated slug before approving


class SignupReject(BaseModel):
    reason: str = ""


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
    # Bank transfer (Opción B de pago) — datos mostrados al cliente
    bank_enabled: Optional[bool] = None
    bank_name: Optional[str] = None
    bank_holder: Optional[str] = None
    bank_clabe: Optional[str] = None
    bank_account: Optional[str] = None
    bank_usd_account: Optional[str] = None
    bank_swift: Optional[str] = None
    bank_aba: Optional[str] = None
    bank_address: Optional[str] = None
    # Per-company outbound email (SMTP/IMAP o Gmail OAuth)
    email_provider: Optional[Literal["resend", "smtp", "gmail"]] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    # Gmail OAuth (cada empresa registra su propio Client ID/Secret de Google)
    gmail_client_id: Optional[str] = None
    gmail_client_secret: Optional[str] = None
    gmail_from_name: Optional[str] = None


class SMTPTestInput(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool = True
    smtp_from_email: str
    smtp_from_name: str = ""
    to_email: Optional[str] = None


class ManualPaymentInput(BaseModel):
    amount: float = Field(gt=0)
    method: Literal["transfer", "cash", "card", "other"] = "transfer"
    note: str = ""


class SendPaymentInput(BaseModel):
    channel: Literal["email"] = "email"
    to_email: Optional[str] = None
    public_url: Optional[str] = None


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
    prices_by_occupancy: Dict[str, float]  # base/default: sencilla, doble, triple, cuadruple
    minor_price: float = 0.0
    # Optional per-season overrides: {season_id: {sencilla, doble, triple, cuadruple, minor_price}}
    season_prices: Dict[str, Dict[str, float]] = {}


class SeasonRange(BaseModel):
    start: str  # ISO YYYY-MM-DD
    end: str


class PackageSeason(BaseModel):
    id: Optional[str] = None
    name: str
    ranges: List[SeasonRange] = []


class PackageCreate(BaseModel):
    code: str
    name: str
    nights: int
    description: str = ""
    image_url: str = ""
    itinerary: List[ItineraryDay] = []
    hotels: List[PackageHotel] = []
    seasons: List[PackageSeason] = []
    includes: List[str] = []
    excludes: List[str] = []
    season_start: Optional[str] = None
    season_end: Optional[str] = None
    allowed_start_days: List[int] = []  # 0=Mon .. 6=Sun; empty => any day
    special_departure_dates: List[str] = []  # ISO dates with fixed departures
    status: str = "active"


class PackageUpdate(BaseModel):
    name: Optional[str] = None
    nights: Optional[int] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    itinerary: Optional[List[ItineraryDay]] = None
    hotels: Optional[List[PackageHotel]] = None
    seasons: Optional[List[PackageSeason]] = None
    includes: Optional[List[str]] = None
    excludes: Optional[List[str]] = None
    season_start: Optional[str] = None
    season_end: Optional[str] = None
    allowed_start_days: Optional[List[int]] = None
    special_departure_dates: Optional[List[str]] = None
    status: Optional[str] = None


# ---------- Services (a la carte) ----------
ServiceCategory = Literal["tour", "traslado", "acceso", "extra"]
ServiceUnit = Literal["per_person", "per_group", "per_day", "per_access"]


class ServiceCreate(BaseModel):
    name: str
    category: ServiceCategory = "tour"
    description: str = ""
    net_price: float = 0.0
    public_price: float = 0.0  # if 0, server auto-computes from net via margin_divisor
    unit: ServiceUnit = "per_group"
    per_person: bool = False  # legacy, kept for back-compat
    status: str = "active"


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[ServiceCategory] = None
    description: Optional[str] = None
    net_price: Optional[float] = None
    public_price: Optional[float] = None
    unit: Optional[ServiceUnit] = None
    per_person: Optional[bool] = None
    status: Optional[str] = None


class SelectedService(BaseModel):
    service_id: str
    qty: int = Field(default=0, ge=0)  # 0 => server computes default by unit


# ---------- Clients ----------
class ClientCreate(BaseModel):
    name: str
    phone: str = ""
    email: str = ""
    channel: Literal["directo", "agencia", "mayorista", "operador"] = "directo"
    notes: str = ""


# ---------- Quotation contacts (agency + final traveler) ----------
class AgencyContact(BaseModel):
    name: str = ""
    contact: str = ""
    email: str = ""


class TravelerContact(BaseModel):
    name: str = ""
    phone: str = ""


class QuotationContacts(BaseModel):
    agency: AgencyContact = Field(default_factory=AgencyContact)
    traveler: TravelerContact = Field(default_factory=TravelerContact)


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
    start: str = ""
    end: str = ""


class ExtraNights(BaseModel):
    cost_per_night: float = Field(default=0.0, ge=0)
    unit: Literal["per_person", "per_room", "per_reservation"] = "per_reservation"


# ---------- Custom / "Programa personalizado" (cotización a medida libre) ----------
CustomUnit = Literal["per_person", "per_night", "per_room", "per_group", "per_day", "per_vehicle"]
CustomCategory = Literal["hospedaje", "traslado", "tour", "extra"]


class CustomItem(BaseModel):
    category: CustomCategory = "extra"
    name: str = ""
    description: str = ""
    net_price: float = Field(default=0.0, ge=0)
    unit: CustomUnit = "per_group"
    qty: int = Field(default=0, ge=0)  # 0 => server computes default by unit


class CustomDay(BaseModel):
    day: int = 1
    title: str = ""
    description: str = ""


class QuotationCreate(BaseModel):
    client_id: str
    type: Literal["paquete", "servicios", "personalizado"] = "paquete"
    package_id: Optional[str] = None
    hotel_name: str = ""
    dates: QuotationDates = Field(default_factory=QuotationDates)
    pax: QuotationPax = Field(default_factory=QuotationPax)
    services: List[SelectedService] = []
    extra_nights: Optional[ExtraNights] = None
    contacts: Optional[QuotationContacts] = None
    notes: str = ""
    assigned_to: Optional[str] = None
    # Custom / programa personalizado
    custom_title: str = ""
    custom_items: List[CustomItem] = []
    custom_itinerary: List[CustomDay] = []
    custom_includes: List[str] = []
    custom_excludes: List[str] = []
    custom_nights: int = Field(default=0, ge=0)
    custom_rooms: int = Field(default=0, ge=0)


class QuotationStateUpdate(BaseModel):
    state: Literal["nueva_consulta", "cotizando", "enviada", "negociacion", "ganada", "perdida"]


class QuotationArchive(BaseModel):
    archived: bool = True


class QuotationUpdate(BaseModel):
    dates: Optional[QuotationDates] = None
    pax: Optional[QuotationPax] = None
    hotel_name: Optional[str] = None
    services: Optional[List[SelectedService]] = None
    extra_nights: Optional[ExtraNights] = None
    contacts: Optional[QuotationContacts] = None
    notes: Optional[str] = None
    assigned_to: Optional[str] = None
    # Custom / programa personalizado
    custom_title: Optional[str] = None
    custom_items: Optional[List[CustomItem]] = None
    custom_itinerary: Optional[List[CustomDay]] = None
    custom_includes: Optional[List[str]] = None
    custom_excludes: Optional[List[str]] = None
    custom_nights: Optional[int] = None
    custom_rooms: Optional[int] = None
