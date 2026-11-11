import pytest

from miniops import ports


@pytest.mark.parametrize("name", ports.__all__)
def test_every_port_is_an_interface_not_an_implementation(name: str) -> None:
    port = getattr(ports, name)

    with pytest.raises(TypeError, match="Protocols cannot be instantiated"):
        port()


def test_the_package_exposes_the_five_ports() -> None:
    assert sorted(ports.__all__) == [
        "ArtifactStore",
        "Executor",
        "ImageRegistry",
        "MetadataStore",
        "ServingBackend",
    ]
