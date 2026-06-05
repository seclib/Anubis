from anubis import CapabilityId, CapabilityManifest


def test_default_capabilities_match_anubis_promises():
    manifest = CapabilityManifest()
    capability_ids = {capability.id for capability in manifest.all()}

    assert capability_ids == {
        CapabilityId.TASK_UNDERSTANDING,
        CapabilityId.POST_ACTION_REFLECTION,
        CapabilityId.SAFE_PATCH_PROPOSAL,
        CapabilityId.EXPLOITABLE_MEMORY,
        CapabilityId.SELF_DEFENSE,
        CapabilityId.SWARM_EMERGENCE,
    }


def test_capability_manifest_verifies_backing_components():
    manifest = CapabilityManifest()
    results = manifest.verify()

    assert all(result.available for result in results)
    assert all(result.checked_components for result in results)
    assert all(result.missing_components == () for result in results)


def test_capability_explanation_is_stable_and_operational():
    manifest = CapabilityManifest()
    explanation = manifest.explain(CapabilityId.SELF_DEFENSE)

    assert explanation[0].startswith("Se defendre:")
    assert any("anubis.safety.SafetyMonitor" in line for line in explanation)
    assert any("kill switch" in line for line in explanation)
