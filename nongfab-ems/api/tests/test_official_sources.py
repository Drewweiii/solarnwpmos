"""Tests for the EGAT / PEA / กกพ / PTT LNG provenance + staleness watcher.

The HTML fragments below mirror how these agencies actually link their
documents (percent-encoded Thai filenames, site-relative hrefs, mixed case
extensions), captured from the real pages on 2026-07-25.
"""

from __future__ import annotations

from datetime import datetime, timezone

from nongfab_api.official_sources import (
    SOURCES,
    STATUS_CHANGED,
    STATUS_OK,
    STATUS_UNREACHABLE,
    OfficialSource,
    diff_documents,
    evaluate,
    extract_document_names,
    overall_status,
)

NOW = datetime(2026, 7, 25, 6, 0, tzinfo=timezone.utc)

# Thai filenames arrive percent-encoded, exactly like this, on both pea.co.th
# and erc.or.th.
# (the UGT2 href is split only to keep the line under the lint limit - it is
# one unbroken URL on the real page)
_UGT2_HREF = (
    "/sites/default/files/users/user34/attachments/"
    "%E0%B8%9B%E0%B8%A3%E0%B8%B0%E0%B8%81%E0%B8%B2%E0%B8%A8"
    "%20%E0%B8%81%E0%B8%9F%E0%B8%A0.%20UGT2.pdf"
)
PEA_HTML = (
    '<a href="/sites/default/files/documents/tariff/electricity_tariff.pdf">อัตรา</a>\n'
    f'<a href="{_UGT2_HREF}">UGT2</a>\n'
)


def source(**kwargs) -> OfficialSource:
    base = dict(
        key="test",
        agency="ทดสอบ",
        agency_full="ทดสอบ",
        page_url="https://example.invalid/",
        purpose="ทดสอบ",
        baseline_documents=("electricity_tariff.pdf", "ประกาศ กฟภ. UGT2.pdf"),
    )
    base.update(kwargs)
    return OfficialSource(**base)  # type: ignore[arg-type]


class TestExtractDocumentNames:
    def test_percent_encoded_thai_filenames_come_back_readable(self):
        names = extract_document_names(PEA_HTML)
        assert names == ["electricity_tariff.pdf", "ประกาศ กฟภ. UGT2.pdf"]

    def test_only_the_filename_is_kept_so_a_moved_file_is_not_a_new_document(self):
        # Agencies reorganise directories without reissuing anything.
        moved = '<a href="/newfolder/2026/electricity_tariff.pdf">x</a>'
        assert extract_document_names(moved) == ["electricity_tariff.pdf"]

    def test_uppercase_extensions_and_duplicates_are_handled(self):
        html = '<a href="/a/Doc.PDF">1</a><a href="/b/Doc.PDF">2</a><a href="/a/other.pdf">3</a>'
        assert extract_document_names(html) == ["Doc.PDF", "other.pdf"]

    def test_a_page_with_no_documents_yields_an_empty_list(self):
        assert extract_document_names("<p>ไม่มีเอกสาร</p>") == []


class TestDiff:
    def test_no_change_reports_nothing(self):
        assert diff_documents(("a.pdf", "b.pdf"), ["b.pdf", "a.pdf"]) == ([], [])

    def test_a_new_announcement_shows_up_as_added(self):
        added, removed = diff_documents(("a.pdf",), ["a.pdf", "ประกาศ กฟภ. UGT2 2570.pdf"])
        assert added == ["ประกาศ กฟภ. UGT2 2570.pdf"]
        assert removed == []

    def test_a_withdrawn_document_shows_up_as_removed(self):
        added, removed = diff_documents(("a.pdf", "b.pdf"), ["a.pdf"])
        assert (added, removed) == ([], ["b.pdf"])


class TestEvaluate:
    def test_an_unchanged_page_is_ok_and_says_how_many_documents_it_saw(self):
        check = evaluate(source(), PEA_HTML, NOW)
        assert check.status == STATUS_OK
        assert "2 ฉบับ" in check.detail
        assert check.added == [] and check.removed == []

    def test_a_new_official_document_flags_the_quoted_values_as_worth_rechecking(self):
        html = PEA_HTML + '<a href="/x/%E0%B8%9B%E0%B8%A3%E0%B8%B0%E0%B8%81%E0%B8%B2%E0%B8%A8%202570.pdf">ใหม่</a>'
        check = evaluate(source(), html, NOW)
        assert check.status == STATUS_CHANGED
        assert check.added == ["ประกาศ 2570.pdf"]
        assert "ตรวจสอบว่าค่าที่เว็บนี้ใช้อยู่ยังตรงกับประกาศล่าสุด" in check.detail

    def test_an_unreachable_page_is_never_reported_as_unchanged(self):
        # Absence of evidence is not evidence of absence - the whole point of
        # the watcher is to notice a change, so a failed fetch must say so.
        check = evaluate(source(), None, NOW)
        assert check.status == STATUS_UNREACHABLE
        assert check.added == [] and check.documents_now == []

    def test_a_page_that_publishes_no_documents_is_reachability_only(self):
        check = evaluate(source(watch_documents=False, baseline_documents=()), "<p>hello</p>", NOW)
        assert check.status == STATUS_OK
        assert "ไม่ได้เผยแพร่เป็นไฟล์เอกสาร" in check.detail

    def test_removal_alone_still_flags_a_change(self):
        check = evaluate(source(), '<a href="/x/electricity_tariff.pdf">x</a>', NOW)
        assert check.status == STATUS_CHANGED
        assert check.removed == ["ประกาศ กฟภ. UGT2.pdf"]


class TestOverallStatus:
    def test_a_real_new_announcement_outranks_a_timeout(self):
        checks = [evaluate(source(), None, NOW), evaluate(source(), PEA_HTML + '<a href="/n.pdf">n</a>', NOW)]
        assert overall_status(checks) == STATUS_CHANGED

    def test_unreachable_wins_over_ok(self):
        assert overall_status([evaluate(source(), PEA_HTML, NOW), evaluate(source(), None, NOW)]) == STATUS_UNREACHABLE

    def test_all_clear_is_ok(self):
        assert overall_status([evaluate(source(), PEA_HTML, NOW)]) == STATUS_OK


class TestRegistry:
    def test_all_four_agencies_the_user_asked_for_are_represented(self):
        agencies = {s.agency for s in SOURCES}
        assert agencies == {"กฟผ.", "กฟภ.", "กกพ.", "PTT LNG"}

    def test_every_key_is_unique(self):
        keys = [s.key for s in SOURCES]
        assert len(keys) == len(set(keys))

    def test_every_quoted_value_names_where_it_lives_in_the_code(self):
        # Without this the panel would say "this number is stale" and leave the
        # reader with no way to find it.
        for src in SOURCES:
            for quoted in src.quoted:
                assert quoted.code_location, f"{src.key}/{quoted.label} has no code location"

    def test_document_watching_sources_actually_have_a_baseline(self):
        for src in SOURCES:
            if src.watch_documents:
                assert src.baseline_documents, f"{src.key} watches documents but has no baseline to compare against"

    def test_the_emission_factor_discrepancy_is_recorded_for_the_operator(self):
        # Found while reading กกพ's own UGT criteria: it cites 0.4758 tCO2/MWh
        # where this site uses 0.4999. Not silently changed - published figures
        # are the operator's call - but it must not be quietly forgotten either.
        erc = next(s for s in SOURCES if s.key == "erc_ugt")
        ef = next(q for q in erc.quoted if "Emission Factor" in q.label)
        assert "0.4758" in ef.note
