from __future__ import annotations

from intent_code import manifest


def test_sha_stability_and_sensitivity():
    assert manifest.span_sha("abc") == manifest.span_sha("abc")
    assert manifest.span_sha("abc") != manifest.span_sha("abd")
    assert manifest.file_sha(b"data") == manifest.file_sha(b"data")
    assert manifest.file_sha(b"data") != manifest.file_sha(b"datb")


def test_reserved_constants():
    assert manifest.MANIFEST_KEY.startswith(manifest.RESERVED_PREFIX)
    assert manifest.REPOMAP_KEY.startswith(manifest.RESERVED_PREFIX)


def test_empty_manifest_shape():
    m = manifest.empty_manifest()
    assert m["files"] == {}
    assert m["version"] == 1
