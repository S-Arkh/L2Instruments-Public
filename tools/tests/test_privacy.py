"""Exercise redaction boundaries without storing real credentials or identities."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('privacy', Path(__file__).parents[1] / 'check_privacy.py')
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)


def test_credentials_are_rejected_even_in_dependencies_and_licenses():
    credential = ('gh' + 'p_' + 'a' * 36).encode()
    for name, dependency in [('app.py', False), ('LICENSE', False), ('packages/data', True)]:
        findings = privacy.inspect(name, credential, dependency)
        assert findings
        assert credential.decode() not in '\n'.join(findings)


def test_personal_metadata_and_dates_are_rejected():
    for text in ['/' + 'home' + '/local-person/project',
                 'local-person' + '@' + 'example.org',
                 '-'.join(['2020', '01', '02']),
                 '.'.join(['02', '01', '2020']),
                 ''.join(['2020', '01', '02']),
                 '{"time' + 'stamp": ' + '1700000000}']:
        assert privacy.inspect('docs/report.md', text.encode())


def test_compact_hex_color_is_not_a_date():
    assert not privacy.inspect('fixture.py', b"data_hex='20408080'")


def test_source_notices_reject_emails_but_dependency_notices_are_preserved():
    email = ('upstream' + '@' + 'example.org').encode()
    assert privacy.inspect('third_party/AUTHORS.txt', email)
    assert not privacy.inspect('packages/AUTHORS.txt', email, dependency=True)


def test_relative_paths_and_workflow_token_are_allowed():
    assert not privacy.inspect('docs/layout.md', b'`work/home/`, `work/tmp/`')
    assert not privacy.inspect('workflow.yml', b'GH_TOKEN: ${{ github.token }}')


def test_qt_high_dpi_manifest_paths_are_not_emails():
    asset = 'packages/PySide6/qml/QtQuick/Controls/icons/button' + '@' + '2x.png'
    assert not privacy.inspect('bundle/BUILDINFO.json', ('{"' + asset + '": "hash"}').encode())
    email = 'person' + '@' + 'example.org'
    assert privacy.inspect('bundle/BUILDINFO.json', ('{"author": "' + email + '"}').encode())


def test_tls_parser_markers_are_not_keys_but_key_payloads_are_rejected():
    marker = b'-----BEGIN ' + b'PRIVATE KEY-----'
    assert not privacy.inspect('packages/QtNetwork.dll', marker + b'\0', True)
    assert privacy.inspect('packages/QtNetwork.dll', marker + b'\n' + b'A' * 64, True)
