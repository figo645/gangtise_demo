"""BDD contracts for rich Insight content with inline images."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_published_insight_keeps_sanitized_rich_html_separate_from_llm_text():
    source = (ROOT / "src/domain/ai_services.py").read_text(encoding="utf-8")
    assert 'content_html=""' in source
    assert "cleaned_html = sanitize_portal_html" in source
    assert '"content_html": cleaned_html' in source


def test_insight_drafts_persist_rich_html_with_a_migration():
    source = (ROOT / "src/domain/core_services.py").read_text(encoding="utf-8")
    migration = (ROOT / "sql/postgres/131_review_rich_content_html.sql").read_text(encoding="utf-8")
    assert "content_html" in source
    assert "ADD COLUMN IF NOT EXISTS content_html" in migration
    assert "content_html = EXCLUDED.content_html" in source


def test_web_review_preserves_images_when_ai_returns_text_only():
    source = (ROOT / "templates/kol_workbench.html").read_text(encoding="utf-8")
    assert "kwBuildReviewGeneratedHtml" in source
    assert "kwReviewImagesHtml" in source
    assert "kwInsertReviewImageIntoEditor" in source
    assert "content_html: kwGetReviewPreviewHtml()" in source


def test_h5_review_supports_paste_upload_and_renders_published_rich_html():
    source = (ROOT / "templates/h5.html").read_text(encoding="utf-8")
    assert "installSharedQuillImagePaste" in source
    assert "insertReviewImageH5Editor" in source
    assert "content_html: getReviewPreviewHtml()" in source
    assert "article.contentHtml ? article.contentHtml" in source
    assert "!article.contentHtml && article.userInputSection" in source
