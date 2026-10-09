"""Desired listing state from andp.yml + a deliver/andp metadata tree."""
import os

from andp.listing_source import load_desired


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_reads_a_deliver_metadata_tree(tmp_path):
    md = str(tmp_path / "metadata")
    _write(md, "copyright.txt", "2026 Acme SAS\n")
    _write(md, "primary_category.txt", "SOCIAL_NETWORKING")
    _write(md, "secondary_category.txt", "EDUCATION")
    _write(md, "fr-FR/name.txt", "Acme : amis")
    _write(md, "fr-FR/subtitle.txt", "Chat")
    _write(md, "fr-FR/privacy_url.txt", "https://acme.io/privacy")
    _write(md, "fr-FR/description.txt", "Une app.")
    _write(md, "fr-FR/keywords.txt", "chat,amis")
    _write(md, "fr-FR/release_notes.txt", "Corrections.")
    _write(md, "fr-FR/promotional_text.txt", "Nouveau")
    _write(md, "fr-FR/support_url.txt", "https://acme.io/contact")
    _write(md, "fr-FR/marketing_url.txt", "https://acme.io")
    _write(md, "review_information/first_name.txt", "Ada")
    _write(md, "review_information/demo_required.txt", "false")
    d = load_desired({"metadata_dir": "metadata"}, str(tmp_path), environ={})
    assert d["errors"] == []
    assert d["version"] == {"copyright": "2026 Acme SAS"}
    assert d["categories"] == {"primaryCategory": "SOCIAL_NETWORKING",
                               "secondaryCategory": "EDUCATION"}
    assert d["app_info_localizations"] == {"fr-FR": {
        "name": "Acme : amis", "subtitle": "Chat",
        "privacyPolicyUrl": "https://acme.io/privacy"}}
    assert d["version_localizations"]["fr-FR"] == {
        "description": "Une app.", "keywords": "chat,amis", "whatsNew": "Corrections.",
        "promotionalText": "Nouveau", "supportUrl": "https://acme.io/contact",
        "marketingUrl": "https://acme.io"}
    assert d["review"] == {"contactFirstName": "Ada", "demoAccountRequired": False}


def test_reads_andp_camel_case_files_too(tmp_path):
    md = str(tmp_path / "md")
    _write(md, "en-US/whatsNew.txt", "Fixes")
    _write(md, "en-US/supportUrl.txt", "https://acme.io/help")
    d = load_desired({}, str(tmp_path), metadata_dir=md, environ={})
    assert d["version_localizations"]["en-US"] == {
        "whatsNew": "Fixes", "supportUrl": "https://acme.io/help"}


def test_empty_files_and_media_folders_are_not_fields(tmp_path):
    md = str(tmp_path / "md")
    _write(md, "en-US/keywords.txt", "   \n")
    from media_files import png
    os.makedirs(os.path.join(md, "en-US/screenshots/APP_IPHONE_67"))
    png(os.path.join(md, "en-US/screenshots/APP_IPHONE_67/01.png"), 1290, 2796)
    d = load_desired({"metadata_dir": "md"}, str(tmp_path), environ={})
    assert d["version_localizations"] == {} and d["errors"] == []


def test_default_folder_fills_every_locale(tmp_path):
    md = str(tmp_path / "md")
    _write(md, "default/privacy_url.txt", "https://acme.io/privacy")
    _write(md, "fr-FR/name.txt", "Acme")
    _write(md, "en-US/name.txt", "Acme")
    _write(md, "en-US/privacy_url.txt", "https://acme.io/en/privacy")
    d = load_desired({"metadata_dir": "md"}, str(tmp_path), environ={})
    assert d["app_info_localizations"]["fr-FR"]["privacyPolicyUrl"] == "https://acme.io/privacy"
    assert d["app_info_localizations"]["en-US"]["privacyPolicyUrl"] == "https://acme.io/en/privacy"
    assert "default" not in d["app_info_localizations"]


def test_andp_yml_wins_over_the_metadata_tree(tmp_path):
    md = str(tmp_path / "md")
    _write(md, "copyright.txt", "2025 Old")
    _write(md, "fr-FR/subtitle.txt", "Ancien")
    store = {"metadata_dir": "md", "version": {"copyright": "2026 New"},
             "localizations": {"fr-FR": {"subtitle": "Nouveau"}}}
    d = load_desired(store, str(tmp_path), environ={})
    assert d["version"]["copyright"] == "2026 New"
    assert d["app_info_localizations"]["fr-FR"]["subtitle"] == "Nouveau"


def test_length_violation_in_a_file_names_the_locale(tmp_path):
    md = str(tmp_path / "md")
    _write(md, "de-DE/keywords.txt", "k" * 101)
    d = load_desired({"metadata_dir": "md"}, str(tmp_path), environ={})
    assert d["errors"] == ["de-DE: keywords: 101 characters, the App Store allows 100"]


def test_secrets_come_from_the_environment_or_an_env_file(tmp_path):
    _write(str(tmp_path), "fastlane/.env", "DEMO_USER=reviewer\nexport DEMO_PASSWORD='s3cr3t'\n# c\n")
    store = {"env_file": "fastlane/.env",
             "review": {"demo_account_required": True,
                        "demo_account_name_env": "DEMO_USER",
                        "demo_account_password_env": "DEMO_PASSWORD",
                        "contact_email_env": "REVIEW_EMAIL"}}
    d = load_desired(store, str(tmp_path), environ={"REVIEW_EMAIL": "ada@acme.io"})
    assert d["errors"] == []
    assert d["review"] == {"demoAccountRequired": True, "demoAccountName": "reviewer",
                           "demoAccountPassword": "s3cr3t", "contactEmail": "ada@acme.io"}


def test_missing_env_variable_is_an_error_without_leaking_anything(tmp_path):
    d = load_desired({"review": {"demo_account_password_env": "NOPE"}}, str(tmp_path),
                     environ={})
    assert d["errors"] == ["store.review: environment variable NOPE is not set"]


def test_file_references_are_read_relative_to_the_project(tmp_path):
    _write(str(tmp_path), "review/notes.md", "Sign in, then tap Chat.\n")
    _write(str(tmp_path), "legal/eula.txt", "Terms.")
    store = {"review": {"notes_file": "review/notes.md", "attachments": ["review/notes.md"]},
             "eula": {"file": "legal/eula.txt", "territories": "all"}}
    d = load_desired(store, str(tmp_path), environ={})
    assert d["errors"] == []
    assert d["review"] == {"notes": "Sign in, then tap Chat."}
    assert d["review_attachments"] == [str(tmp_path / "review/notes.md")]
    assert d["eula"] == {"text": "Terms.", "territories": "all"}


def test_standard_eula_and_phased_release(tmp_path):
    d = load_desired({"eula": "standard", "version": {"phased_release": True,
                                                      "release_type": "AFTER_APPROVAL"}},
                     str(tmp_path), environ={})
    assert d["errors"] == []
    assert d["eula"] == {"standard": True}
    assert d["phased_release"] is True
    assert d["version"] == {"releaseType": "AFTER_APPROVAL"}


def test_accessibility_is_declared_per_device_family(tmp_path):
    store = {"accessibility": {"iphone": {"voiceover": True, "dark_interface": True},
                               "IPAD": {"supportsLargerText": False}}}
    d = load_desired(store, str(tmp_path), environ={})
    assert d["errors"] == []
    assert d["accessibility"] == {
        "IPHONE": {"supportsVoiceover": True, "supportsDarkInterface": True},
        "IPAD": {"supportsLargerText": False}}
    bad = load_desired({"accessibility": {"PHONE": {"voiceover": True}}}, str(tmp_path),
                       environ={})
    assert bad["errors"] and "PHONE" in bad["errors"][0]


def test_encryption_declaration_needs_every_answer(tmp_path):
    d = load_desired({"encryption": {"app_description": "E2EE messaging",
                                     "contains_proprietary_cryptography": False}},
                     str(tmp_path), environ={})
    assert any("containsThirdPartyCryptography" in e for e in d["errors"])


def test_unknown_store_section_is_an_error_but_known_ones_are_not(tmp_path):
    d = load_desired({"pricing": {"price": "free"}, "age_rating": {}, "availability": {},
                      "platform": "IOS", "listing": {}}, str(tmp_path), environ={})
    assert d["errors"] == ["store: unknown section 'listing'"]


def test_cross_field_rules_are_reported(tmp_path):
    d = load_desired({"version": {"release_type": "SCHEDULED"},
                      "review": {"demo_account_required": True}}, str(tmp_path), environ={})
    assert "earliestReleaseDate is required when releaseType is SCHEDULED" in d["errors"]
    assert "demoAccountName is required when demoAccountRequired is true" in d["errors"]


def test_missing_metadata_dir_is_an_error(tmp_path):
    d = load_desired({"metadata_dir": "nowhere"}, str(tmp_path), environ={})
    assert d["errors"] and "nowhere" in d["errors"][0]


def test_media_of_the_metadata_tree_is_part_of_the_desired_listing(tmp_path):
    from media_files import png
    folder = tmp_path / "md" / "fr-FR" / "screenshots" / "IPHONE_DUO"
    folder.mkdir(parents=True)
    png(str(folder / "01.png"), 2007, 2853)
    png(str(folder / "02.png"), 10, 10)
    d = load_desired({"metadata_dir": "md", "media": {"prune": True}}, str(tmp_path),
                     environ={})
    assert list(d["media"]["fr-FR"]) == [("APP_SCREENSHOT", "IPHONE_DUO_PROFILE")]
    assert d["media_prune"] is True
    assert any("02.png" in e and "10×10" in e for e in d["errors"])
