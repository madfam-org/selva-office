"""
E2E tests — Gap 4: SKILL.md Progressive Disclosure Format
"""
from pathlib import Path

SAMPLE_SKILL_MD = """---
name: deploy-k8s
description: Deploy a service to Kubernetes
version: 1.2.0
platforms:
  - macos
  - linux
metadata:
  hermes:
    tags: [kubernetes, devops]
    category: devops
---
# Deploy to Kubernetes

## When to Use
When you need to deploy a containerized service to a K8s cluster.

## Procedure
1. Build the Docker image
2. Push to registry
3. Apply manifests

## Pitfalls
- Ensure the namespace exists before applying

## Verification
Run `kubectl rollout status deployment/my-service`
"""

SAMPLE_REFERENCE = "# K8s Reference\nSee kubernetes.io for full API docs."


class TestSkillMDRegistry:
    def _build_skill_dir(self, tmp_path: Path) -> Path:
        skill_dir = tmp_path / "devops" / "deploy-k8s"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL_MD)
        ref_dir = skill_dir / "references"
        ref_dir.mkdir()
        (ref_dir / "k8s-api.md").write_text(SAMPLE_REFERENCE)
        return tmp_path

    def test_load_md_skills_discovers_skill(self, tmp_path):
        """SKILL.md in the skills dir is loaded into the registry."""
        self._build_skill_dir(tmp_path)
        from selva_skills.skill_md import SkillMDRegistry
        registry = SkillMDRegistry(skills_dir=str(tmp_path))
        registry.load_md_skills()
        assert "deploy-k8s" in registry.get_all_md_skills()

    def test_level_0_compact_list(self, tmp_path):
        """Level 0: list_skills_compact() returns only name, description, category."""
        self._build_skill_dir(tmp_path)
        from selva_skills.skill_md import SkillMDRegistry
        registry = SkillMDRegistry(skills_dir=str(tmp_path))
        registry.load_md_skills()
        compact = registry.list_skills_compact()
        assert len(compact) == 1
        entry = compact[0]
        assert set(entry.keys()) == {"name", "description", "category"}
        assert entry["name"] == "deploy-k8s"
        assert entry["category"] == "devops"

    def test_level_1_full_content(self, tmp_path):
        """Level 1: get_skill_full() returns full SKILL.md content."""
        self._build_skill_dir(tmp_path)
        from selva_skills.skill_md import SkillMDRegistry
        registry = SkillMDRegistry(skills_dir=str(tmp_path))
        registry.load_md_skills()
        content = registry.get_skill_full("deploy-k8s")
        assert content is not None
        assert "Kubernetes" in content
        assert "Procedure" in content

    def test_level_2_reference_file(self, tmp_path):
        """Level 2: get_skill_reference() returns specific reference file."""
        self._build_skill_dir(tmp_path)
        from selva_skills.skill_md import SkillMDRegistry
        registry = SkillMDRegistry(skills_dir=str(tmp_path))
        registry.load_md_skills()
        ref = registry.get_skill_reference("deploy-k8s", "k8s-api.md")
        assert ref is not None
        assert "kubernetes.io" in ref

    def test_missing_skill_returns_none(self, tmp_path):
        """get_skill_full() returns None for unknown skill names."""
        from selva_skills.skill_md import SkillMDRegistry
        registry = SkillMDRegistry(skills_dir=str(tmp_path))
        registry.load_md_skills()
        assert registry.get_skill_full("nonexistent-skill") is None

    def test_compact_list_token_budget(self, tmp_path):
        """Compact list for a 50-skill set stays well under 3,200 tokens."""
        # Create 50 minimal skills
        for i in range(50):
            skill_dir = tmp_path / f"skill-{i:02d}"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: skill-{i:02d}\ndescription: Test skill {i}\n---\n# Skill {i}\n"
            )
        import json

        from selva_skills.skill_md import SkillMDRegistry
        registry = SkillMDRegistry(skills_dir=str(tmp_path))
        registry.load_md_skills()
        compact = registry.list_skills_compact()
        serialized = json.dumps(compact)
        approx_tokens = len(serialized) // 4
        assert approx_tokens < 3200, f"Compact list exceeds token budget: ~{approx_tokens} tokens"
