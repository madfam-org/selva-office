"""Test tenant data isolation via org_id scoping.

Verifies that the RLS middleware and all tenant-scoped models enforce
org_id boundaries correctly.
"""

from __future__ import annotations

import pytest

from nexus_api.middleware.security import org_id_var


class TestTenantIsolation:
    def test_org_id_context_var_default(self) -> None:
        """Default org_id should be 'default'."""
        assert org_id_var.get() == "default"

    def test_org_id_context_var_set_and_reset(self) -> None:
        """Setting org_id context var should persist until reset."""
        token = org_id_var.set("org-123")
        assert org_id_var.get() == "org-123"
        org_id_var.reset(token)
        assert org_id_var.get() == "default"

    def test_org_id_context_var_nested(self) -> None:
        """Nested org_id context var sets should unwind correctly."""
        token1 = org_id_var.set("org-aaa")
        token2 = org_id_var.set("org-bbb")
        assert org_id_var.get() == "org-bbb"
        org_id_var.reset(token2)
        assert org_id_var.get() == "org-aaa"
        org_id_var.reset(token1)
        assert org_id_var.get() == "default"

    def test_all_models_have_org_id(self) -> None:
        """Every model that stores tenant data must have an org_id column."""
        from nexus_api.models import (
            Agent,
            ApprovalRequest,
            Artifact,
            CalendarConnection,
            ChatMessage,
            ComputeTokenLedger,
            Department,
            Map,
            SkillMarketplaceEntry,
            SkillRating,
            SwarmTask,
            TaskEvent,
            TenantConfig,
            Workflow,
        )

        org_scoped_models = [
            Department,
            Agent,
            ApprovalRequest,
            SwarmTask,
            Workflow,
            Artifact,
            ComputeTokenLedger,
            SkillMarketplaceEntry,
            SkillRating,
            CalendarConnection,
            Map,
            TaskEvent,
            ChatMessage,
            TenantConfig,
        ]
        for model in org_scoped_models:
            assert hasattr(model, "org_id"), f"{model.__name__} missing org_id column"

    def test_tenant_config_org_id_unique(self) -> None:
        """TenantConfig.org_id must be unique to prevent duplicate provisioning."""
        from nexus_api.models import TenantConfig

        for col in TenantConfig.__table__.columns:
            if col.name == "org_id":
                assert col.unique, "TenantConfig.org_id must be unique"
                break
        else:
            pytest.fail("TenantConfig has no org_id column")

    def test_tenant_config_has_sso_and_branding_columns(self) -> None:
        """TenantConfig must have the enterprise SSO and branding columns."""
        from nexus_api.models import TenantConfig

        col_names = {c.name for c in TenantConfig.__table__.columns}
        assert "janua_connection_id" in col_names
        assert "brand_name" in col_names
        assert "brand_logo_url" in col_names
        assert "brand_primary_color" in col_names
