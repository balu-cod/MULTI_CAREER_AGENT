"""Shared vocabulary + matching helpers used by the matcher, tailor, resume builder and page scraper."""
import re

TECH = ["python", "java", "javascript", "typescript", "react", "next.js", "node", "fastapi", "django", "flask", "sql", "postgresql", "supabase", "mongodb",
        "redis", "docker", "kubernetes", "aws", "azure", "gcp", "linux", "git", "rest", "graphql", "langchain", "langgraph", "mcp", "llm", "rag", "pytorch",
        "tensorflow", "dsa", "ci/cd", "php", "c++"]


def has_term(term, text):
    """Whole-word, case-insensitive match that is safe for terms like c++, ci/cd and next.js."""
    return re.search(r"(?<![\w+#/])" + re.escape(str(term).lower()) + r"(?![\w+#/])", str(text).lower()) is not None
