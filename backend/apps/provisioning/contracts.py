"""
Contrat des appels de la plateforme — COPIE EXACTE de
nfc/backend/apps/tenants/contracts.py (plateforme SigmaGravity).

Ne pas modifier ici seulement : la plateforme envoie ce format. Un champ en
trop ou en moins et chaque appel est refusé (extra="forbid", strict=True).
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProvisionSolution(ContractModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9-]{1,39}$")
    environment: Literal["dev", "prod"]


class ProvisionTenant(ContractModel):
    external_id: UUID
    slug: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
    display_name: str = Field(min_length=1, max_length=180)
    is_demo: bool = False


class ProvisionOwner(ContractModel):
    external_user_id: UUID | None = None
    name: str = Field(min_length=1, max_length=180)
    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    username: str = Field(min_length=2, max_length=80)


class ProvisionModule(ContractModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    enabled: bool


class ProvisionSubscription(ContractModel):
    plan_key: str = Field(min_length=1, max_length=80)
    revision: int = Field(ge=1)
    modules: list[ProvisionModule] = Field(default_factory=list)
    limits: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def module_keys_are_unique(self):
        keys = [module.key for module in self.modules]
        if len(keys) != len(set(keys)):
            raise ValueError("module keys must be unique")
        return self


class ProvisionTemplate(ContractModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class ProvisionDomains(ContractModel):
    platform_hostname: str = Field(min_length=4, max_length=253)
    custom_hostnames: list[str] = Field(default_factory=list)


class TenantProvisionRequest(ContractModel):
    event_id: UUID
    action: Literal["create_tenant"]
    solution: ProvisionSolution
    tenant: ProvisionTenant
    owner: ProvisionOwner
    subscription: ProvisionSubscription
    template: ProvisionTemplate | None = None
    domains: ProvisionDomains


class EntitlementUpdateRequest(ContractModel):
    event_id: UUID
    action: Literal["update_entitlements"]
    solution: ProvisionSolution
    tenant_external_id: UUID
    subscription: ProvisionSubscription


class DemoResetRequest(ContractModel):
    event_id: UUID
    action: Literal["reset_demo"]
    solution: ProvisionSolution
    tenant_external_id: UUID
    template: ProvisionTemplate
    expected_current_version: str | None = None
