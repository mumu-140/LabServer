def test_workspace_packages_import() -> None:
    import labserver_contracts
    import labserver_core

    assert labserver_contracts.__name__ == "labserver_contracts"
    assert labserver_core.__name__ == "labserver_core"
