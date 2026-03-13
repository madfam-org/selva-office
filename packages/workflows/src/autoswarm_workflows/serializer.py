"""YAML serialization and deserialization for workflow definitions."""

from __future__ import annotations

import yaml

from .schema import WorkflowDefinition


class WorkflowSerializer:
    """Serialize/deserialize WorkflowDefinition to/from YAML."""

    @staticmethod
    def to_yaml(workflow: WorkflowDefinition) -> str:
        """Serialize a workflow definition to a YAML string."""
        # mode="json" ensures enums are serialized as plain strings, not Python objects
        data = workflow.model_dump(exclude_defaults=True, mode="json")
        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    @staticmethod
    def from_yaml(yaml_content: str) -> WorkflowDefinition:
        """Deserialize a YAML string into a WorkflowDefinition.

        Raises:
            yaml.YAMLError: If the YAML is malformed.
            pydantic.ValidationError: If the parsed data doesn't match the schema.
        """
        data = yaml.safe_load(yaml_content)
        if not isinstance(data, dict):
            msg = f"Expected a YAML mapping at top level, got {type(data).__name__}"
            raise ValueError(msg)
        return WorkflowDefinition.model_validate(data)

    @staticmethod
    def to_dict(workflow: WorkflowDefinition) -> dict:
        """Serialize a workflow definition to a plain dict."""
        return workflow.model_dump(exclude_defaults=True, mode="json")

    @staticmethod
    def from_dict(data: dict) -> WorkflowDefinition:
        """Deserialize a dict into a WorkflowDefinition."""
        return WorkflowDefinition.model_validate(data)
