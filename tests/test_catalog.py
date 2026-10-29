from app.catalog import catalog_as_prompt_text, catalog_names, load_catalog


def test_catalog_loads_and_is_nonempty():
    assert len(load_catalog()) >= 10


def test_known_products_present():
    assert {"TenantEase", "Revio", "Cynbit Studio"} <= catalog_names()


def test_all_sources_are_cynbit_pages():
    for e in load_catalog():
        assert str(e.source_url).startswith("https://www.cynbit.in/")


def test_every_service_has_a_category_and_products_do_not():
    for e in load_catalog():
        assert (e.category is not None) == (e.kind == "service")


def test_prompt_text_mentions_every_entry():
    text = catalog_as_prompt_text()
    for name in catalog_names():
        assert name in text
