"""
Tra cứu cấu trúc kho văn bản của miền giao thông.

Engine cần biết "Điều 57 của Luật 36/2024 có thật không" để quyết định có đưa một căn cứ vào
khối nguồn hay không, nhưng cách đánh số mục là của từng miền — văn bản quy phạm pháp luật
Việt Nam dùng Chương > Điều > Khoản > Điểm, một miền khác dùng cách hoàn toàn khác. Vì vậy
phần tra này do miền cung cấp, khai báo ở `corpus.article_exists` trong domain.yaml.
"""


def article_exists(doc_id: str, number: int) -> bool:
    """Điều số `number` có tồn tại trong văn bản `doc_id` không."""
    from domains.vietnam_traffic.lib.document_provider import get_document_provider

    provider = get_document_provider()
    try:
        if number in (provider._articles_content.get(doc_id) or {}):
            return True
        tree = provider._trees.get(doc_id) or {}
        for chapter in tree.get("chapters", []):
            for article in chapter.get("articles", []):
                if int(article.get("article_number", -1)) == number:
                    return True
        return False
    except Exception:
        # Không tra được thì không kết luận là sai: thà hiển thị thừa còn hơn giấu mất căn cứ.
        return True
